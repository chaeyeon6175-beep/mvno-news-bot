import os, requests, re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor

# ──────────────────────────────────────────
# 1. 환경 변수 설정
# ──────────────────────────────────────────
from dotenv import load_dotenv

load_dotenv()

NAVER_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")

DB_IDS = {
    "MNO": os.environ.get("DB_ID_MNO"),
    "SUBSID": os.environ.get("DB_ID_SUBSID"),
    "FIN": os.environ.get("DB_ID_FIN"),
    "SMALL": os.environ.get("DB_ID_SMALL"),
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# ──────────────────────────────────────────
# 2. 키워드 기반 영향도 분석
# ──────────────────────────────────────────
KEYWORDS_HIGH = [
    "도매대가", "도매제공", "접속료", "망이용대가", "망사용료",
    "과기정통부", "방통위", "전파법", "통신정책", "규제", "의무",
    "전기통신사업법", "인가", "허가", "시정명령", "제재", "과징금",
    "요금인하", "요금인상", "요금제 출시", "무제한", "가격경쟁",
    "망품질", "통화품질", "속도제한", "데이터차별", "품질저하", 
    "알뜰폰 정책", "알뜰폰 규제", "알뜰폰 지원", "MVNO 점유",
]

KEYWORDS_MID = [
    "단말", "갤럭시", "아이폰", "출시", "신제품", "폴드", "플립",
    "마케팅", "프로모션", "보조금", "공시지원금", "번호이동",
    "가입자", "점유율", "해지", "이탈", "순증", "시장점유",
    "결합상품", "결합할인", "인터넷결합", "IPTV", "알뜰폰", 
    "eSIM", "유심", "로밍", "제휴", "협업", "MOU",
    "실적", "매출", "영업이익",
]

REASONS_HIGH = {
    "도매대가": "도매대가 변동", "도매제공": "도매대가 변동",
    "접속료": "접속료 변동", "망이용대가": "망이용대가 변동",
    "망사용료": "망사용료 변동", "과기정통부": "정책/규제 변화",
    "방통위": "정책/규제 변화", "전파법": "정책/규제 변화",
    "통신정책": "정책/규제 변화", "규제": "규제 변화",
    "의무": "규제 변화", "전기통신사업법": "법률 변화",
    "인가": "정책/규제 변화", "허가": "정책/규제 변화",
    "시정명령": "규제 제재", "제재": "규제 제재", "과징금": "규제 제재",
    "요금인하": "요금제 경쟁", "요금인상": "요금제 변동",
    "요금제 출시": "요금제 경쟁", "무제한": "요금제 경쟁",
    "가격경쟁": "요금제 경쟁", "망품질": "망 품질 이슈",
    "통화품질": "망 품질 이슈", "속도제한": "망 품질 이슈",
    "데이터차별": "망 품질 이슈", "품질저하": "망 품질 이슈",
    "알뜰폰 정책": "알뜰폰 정책 변화", "알뜰폰 규제": "알뜰폰 규제 변화",
    "알뜰폰 지원": "알뜰폰 지원 정책", "MVNO 점유": "MVNO 시장 변동",
}

REASONS_MID = {
    "단말": "단말 동향", "갤럭시": "단말 출시", "아이폰": "단말 출시",
    "출시": "신규 출시", "신제품": "단말 출시", "폴드": "단말 출시",
    "플립": "단말 출시", "마케팅": "MNO 마케팅 변화",
    "프로모션": "MNO 마케팅 변화", "보조금": "보조금 동향",
    "공시지원금": "보조금 동향", "번호이동": "소비자 이동 동향",
    "가입자": "가입자 동향", "점유율": "시장 점유 변화",
    "해지": "가입자 이탈", "이탈": "가입자 이탈", "순증": "가입자 동향",
    "시장점유": "시장 점유 변화", "결합상품": "결합상품 동향",
    "결합할인": "결합상품 동향", "인터넷결합": "결합상품 동향",
    "IPTV": "결합상품 동향", "eSIM": "eSIM 동향", "유심": "유심 동향",
    "로밍": "로밍 동향", "제휴": "제휴/협업", "협업": "제휴/협업",
    "MOU": "제휴/협업", "실적": "실적 발표", "매출": "실적 발표",
    "영업이익": "실적 발표",
}


def analyze_impact(title: str) -> dict:
    """키워드 매칭으로 영향도 분석"""
    t = title.lower().replace(" ", "")

    for kw in KEYWORDS_HIGH:
        if kw.replace(" ", "").lower() in t:
            return {
                "impact_level": "🔴 중요",
                "impact_reason": REASONS_HIGH.get(kw, "주요 이슈"),
            }

    for kw in KEYWORDS_MID:
        if kw.replace(" ", "").lower() in t:
            return {
                "impact_level": "🟡 모니터링",
                "impact_reason": REASONS_MID.get(kw, "모니터링 필요"),
            }

    return {"impact_level": "🟢 참고", "impact_reason": "일반 동향"}


# ──────────────────────────────────────────
# 3. 유틸리티 함수
# ──────────────────────────────────────────
def clear_database(db_id):
    """수집 전 기존 기사 삭제 (병렬 처리)"""
    print(f"🧹 데이터베이스 비우기: {db_id}")
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"

    def archive_page(page_id):
        requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=HEADERS,
            json={"archived": True},
        )

    while True:
        res = requests.post(query_url, headers=HEADERS, json={"page_size": 100})
        results = res.json().get("results", [])
        if not results:
            break
        with ThreadPoolExecutor(max_workers=10) as pool:
            pool.map(archive_page, [p["id"] for p in results])
        if not res.json().get("has_more"):
            break


def get_similarity(a, b):
    a = re.sub(r"[^가-힣a-zA-Z0-9]", "", a)
    b = re.sub(r"[^가-힣a-zA-Z0-9]", "", b)
    return SequenceMatcher(None, a, b).ratio()


def get_word_overlap(a, b):
    """단어 기반 Jaccard 유사도 (1글자 조사/접속사 제외)"""
    def extract_words(text):
        words = re.findall(r"[가-힣a-zA-Z0-9]+", text)
        return set(w for w in words if len(w) >= 2)
    words_a = extract_words(a)
    words_b = extract_words(b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def is_duplicate(title, seen_titles):
    """문자열 유사도 또는 단어 겹침이 높으면 중복으로 판단"""
    for st in seen_titles:
        if get_similarity(title, st) > 0.40:
            return True
        if get_word_overlap(title, st) > 0.45:
            return True
    return False


def is_telecom_news(title):
    t = title.lower().replace(" ", "")
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "주가", "증시", "상장"]
    if any(ex in t for ex in exclude):
        return False
    include = [
        "요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신",
        "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "출시",
        "모바일", "개통", "선불", "후불", "데이터", "무제한", "할인", "제휴",
        "번호이동", "해지", "보조금", "약정", "셀프개통", "유심칩",
    ]
    return any(inc in t for inc in include)


def get_final_tags(title, db_key, default_tag):
    if not is_telecom_news(title):
        return None
    t = title.lower().replace(" ", "")
    if db_key == "MNO":
        sa3_kws = ["통신3사", "이통3사", "통신업계", "3사"]
        skt, kt, lg = (
            "skt" in t or "sk텔레콤" in t,
            "kt" in t or "케이티" in t,
            "lgu+" in t or "lgu⁺" in t or "lg유플러스" in t or "lgu플러스" in t or "lgu유플러스" in t,
        )
        if any(x in t for x in sa3_kws) or (skt + kt + lg >= 2):
            return [{"name": "통신 3사"}]
        elif skt:
            return [{"name": "SKT"}]
        elif kt:
            return [{"name": "KT"}]
        elif lg:
            return [{"name": "LGU+"}]
        return [{"name": default_tag}]
    maps = {
        "SUBSID": {
            "SK텔링크": ["sk텔링크", "7모바일"],
            "KT M모바일": ["ktm모바일", "kt엠모바일"],
            "LG헬로비전": ["lg헬로비전", "헬로모바일"],
            "KT스카이라이프": ["스카이라이프"],
            "미디어로그": ["미디어로그", "유모바일"],
        },
        "FIN": {
            "토스모바일": ["토스모바일", "토스"],
            "우리원모바일": ["우리원모바일", "우리원"],
            "KB리브모바일": ["리브모바일", "리브m", "kb국민"],
        },
        "SMALL": {
            "아이즈모바일": ["아이즈모바일"],
            "프리모바일": ["프리텔레콤", "프리티"],
            "에넥스텔레콤": ["에넥스텔레콤", "a모바일"],
            "유니컴즈": ["유니컴즈", "모비스트"],
            "인스코비": ["인스코비"],
            "세종텔레콤": ["세종텔레콤", "스노우맨"],
            "큰사람": ["큰사람", "이야기모바일"],
        },
    }
    if db_key in maps:
        for name, kws in maps[db_key].items():
            if any(k in t for k in kws):
                return [{"name": name}]
    return None


# ──────────────────────────────────────────
# 4. Notion 저장
# ──────────────────────────────────────────
def ensure_impact_properties(db_id):
    """영향도/영향도 이유 속성이 없으면 자동 생성"""
    target_id = re.sub(r"[^a-fA-F0-9]", "", db_id)
    res = requests.get(
        f"https://api.notion.com/v1/databases/{target_id}", headers=HEADERS
    )
    if res.status_code != 200:
        print(f"  ⚠️ DB 조회 실패: {res.text[:200]}")
        return
    props = res.json().get("properties", {})
    updates = {}
    if "영향도" not in props:
        updates["영향도"] = {
            "select": {
                "options": [
                    {"name": "🔴 중요", "color": "red"},
                    {"name": "🟡 모니터링", "color": "yellow"},
                    {"name": "🟢 참고", "color": "green"},
                ]
            }
        }
    if "영향도 이유" not in props:
        updates["영향도 이유"] = {"rich_text": {}}
    if "영향도순서" not in props:
        updates["영향도순서"] = {"number": {}}
    if updates:
        print(f"  🔧 영향도 속성 자동 생성 중...")
        patch_res = requests.patch(
            f"https://api.notion.com/v1/databases/{target_id}",
            headers=HEADERS,
            json={"properties": updates},
        )
        if patch_res.status_code == 200:
            print(f"  ✅ 영향도 속성 생성 완료")
        else:
            print(f"  ❌ 속성 생성 실패: {patch_res.text[:200]}")


IMPACT_ORDER = {"🔴 중요": 1, "🟡 모니터링": 2, "🟢 참고": 3}


def post_notion(db_id, title, link, tags, pub_date, impact: dict):
    """Notion에 기사 저장"""
    target_id = re.sub(r"[^a-fA-F0-9]", "", db_id)
    data = {
        "parent": {"database_id": target_id},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": tags},
            "영향도": {"select": {"name": impact["impact_level"]}},
            "영향도 이유": {
                "rich_text": [{"text": {"content": impact["impact_reason"]}}]
            },
            "영향도순서": {"number": IMPACT_ORDER.get(impact["impact_level"], 3)},
        },
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    if res.status_code != 200:
        print(f"  ❌ Notion 저장 실패 ({res.status_code}): {res.text[:200]}")
    return res.status_code == 200


# ──────────────────────────────────────────
# 5. 통합 수집 로직
# ──────────────────────────────────────────
def collect_news(db_key, configs, default_days=7):
    """통합 수집 로직: 분류별 최대 15개, 오늘 오전 9시 이전 기사만"""
    db_id = DB_IDS.get(db_key)
    ensure_impact_properties(db_id)
    clear_database(db_id)

    seen_urls, seen_titles = set(), []
    # 수집 기간: default_days일 전 ~ 오늘 오전 9시
    cutoff_start = datetime.now().replace(hour=0, minute=0, second=0) - timedelta(days=default_days)
    cutoff_end = datetime.now().replace(hour=9, minute=0, second=0)

    for keywords, _, target_tag in configs:
        tag_count = 0
        print(f"📡 {db_key} - {target_tag} 수집 중...")

        for sort in ["sim", "date"]:
            if tag_count >= 5:
                break
            query = " ".join(keywords)
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}"
            res = requests.get(
                url,
                headers={
                    "X-Naver-Client-Id": NAVER_ID,
                    "X-Naver-Client-Secret": NAVER_SECRET,
                },
            )
            if res.status_code != 200:
                continue

            for item in res.json().get("items", []):
                if tag_count >= 5:
                    break
                if item["link"] in seen_urls:
                    continue

                title = (
                    item["title"]
                    .replace("<b>", "")
                    .replace("</b>", "")
                    .replace("&quot;", '"')
                )
                if is_duplicate(title, seen_titles):
                    continue

                tags = get_final_tags(title, db_key, target_tag)
                if tags and tags[0]["name"] == target_tag:
                    pub_dt = datetime.strptime(
                        item["pubDate"], "%a, %d %b %Y %H:%M:%S +0900"
                    )

                    if cutoff_start <= pub_dt <= cutoff_end:
                        p_date = pub_dt.strftime("%Y-%m-%d")
                        impact = analyze_impact(title)
                        print(f"  {impact['impact_level']} | {title[:30]}...")

                        if post_notion(
                            db_id, title, item["link"], tags, p_date, impact
                        ):
                            seen_urls.add(item["link"])
                            seen_titles.append(title)
                            tag_count += 1

        print(f"✅ {target_tag}: {tag_count}개 수집됨\n")


# ──────────────────────────────────────────
# 6. 메인 실행
# ──────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"🗞️  MVNO 뉴스 브리핑: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    collect_news(
        "MNO",
        [
            (["SK텔레콤", "SKT"], 15, "SKT"),
            (["KT", "케이티"], 15, "KT"),
            (["LG유플러스"], 15, "LGU+"),
            (["통신3사", "통신업계"], 15, "통신 3사"),
        ],
        5,
    )

    collect_news(
        "SUBSID",
        [
            (["SK텔링크"], 15, "SK텔링크"),
            (["KT엠모바일"], 15, "KT M모바일"),
            (["LG헬로비전"], 15, "LG헬로비전"),
            (["스카이라이프"], 15, "KT스카이라이프"),
            (["미디어로그"], 15, "미디어로그"),
        ],
        30,
    )

    collect_news(
        "FIN",
        [
            (["토스모바일"], 15, "토스모바일"),
            (["리브모바일"], 15, "KB리브모바일"),
            (["우리원모바일"], 15, "우리원모바일"),
        ],
        60,
    )

    collect_news(
        "SMALL",
        [
            (["아이즈모바일"], 15, "아이즈모바일"),
            (["프리텔레콤"], 15, "프리모바일"),
            (["에넥스텔레콤"], 15, "에넥스텔레콤"),
            (["유니컴즈"], 15, "유니컴즈"),
            (["인스코비"], 15, "인스코비"),
            (["세종텔레콤"], 15, "세종텔레콤"),
            (["큰사람"], 15, "큰사람"),
        ],
        365,
    )

    print(f"\n{'='*50}")
    print(f"🎉 전체 완료!")
    print(f"{'='*50}\n")