import os, requests, re, time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 1. 환경 변수 및 DB ID 설정
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_IDS = {
    "MNO": os.environ.get('DB_ID_MNO'),
    "SUBSID": os.environ.get('DB_ID_SUBSID'),
    "FIN": os.environ.get('DB_ID_FIN'),
    "SMALL": os.environ.get('DB_ID_SMALL')
}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 주요 언론사 가중치 리스트
MAJOR_PRESS = ["연합뉴스", "뉴시스", "뉴스1", "매일경제", "한국경제", "전자신문", "디지털데일리", "머니투데이"]

def get_similarity(a, b):
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def is_telecom_industry_news(title):
    """스포츠, 쇼핑 등 타 산업 기사 원천 차단 필터"""
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "음악회", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "공시지원"]
    return any(inc in t for inc in include)

def select_representative(articles):
    """대표 기사 선정: 메이저 언론사 우선 + 제목 구체성(길이)"""
    best_score = -1
    best_art = articles[0]
    for art in articles:
        score = 0
        if any(p in art['press'] for p in MAJOR_PRESS): score += 10
        score += len(art['title']) * 0.1
        if score >= best_score:
            best_score = score
            best_art = art
    return best_art

def get_strict_db_tags(title, db_key, default_tag):
    """사용자가 정의한 정확한 태그 체계 복구"""
    if not is_telecom_industry_news(title): return None
    t = title.lower().replace(' ', '')

    # 1. MNO DB (이통 3사 전용)
    if db_key == "MNO":
        if any(x in t for x in ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브모바일", "토스모바일", "우리원"]): return None
        is_3사 = any(x in t for x in ["통신3사", "이통3사", "통신사"]) or \
                 (sum([any(x in t for x in ["skt", "sk텔레콤"]), any(x in t for x in ["kt", "케이티"]), any(x in t for x in ["lgu+", "lg유플러스"])]) >= 2)
        if is_3사: return [{"name": "통신 3사"}]
        if any(x in t for x in ["skt", "sk텔레콤"]): return [{"name": "SKT"}]
        if any(x in t for x in ["kt", "케이티"]): return [{"name": "KT"}]
        if any(x in t for x in ["lg유플러스", "lgu+"]): return [{"name": "LG U+"}]

    # 2. 자회사 DB (5개사 고정)
    elif db_key == "SUBSID":
        subsid_map = {
            "SK텔링크": ["sk텔링크", "7모바일"],
            "KT M모바일": ["ktm모바일", "kt엠모바일"],
            "LG헬로비전": ["lg헬로비전", "헬로모바일"],
            "KT스카이라이프": ["스카이라이프"],
            "미디어로그": ["미디어로그", "유모바일"]
        }
        for name, kws in subsid_map.items():
            if any(x in t for x in kws): return [{"name": name}]

    # 3. 금융 DB (지정된 3개사)
    elif db_key == "FIN":
        fin_map = {
            "토스모바일": ["토스모바일"],
            "우리원모바일": ["우리원모바일", "우리원m"],
            "KB리브모바일": ["리브모바일", "리브m"]
        }
        for name, kws in fin_map.items():
            if any(x in t for x in kws): return [{"name": name}]

    # 4. 중소회사 DB (기타 알뜰폰)
    elif db_key == "SMALL":
        if "알뜰폰" not in t: return None
        # 위 1, 2, 3번에 해당하는 주요 키워드가 있으면 제외
        major_kws = ["skt", "sk텔레콤", "kt", "케이티", "lgu+", "lg유플러스", "텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브", "토스", "우리원"]
        if any(x in t for x in major_kws): return None
        return [{"name": "중소 알뜰폰"}]

    return None

def collect(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]

    for keywords, limit, default_tag in configs:
        query = " ".join(keywords)
        raw_items = []
        for sort in ["date", "sim"]:
            res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}",
                               headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))

        # 데이터 정제 및 태그 부여
        valid_articles = []
        for item in raw_items:
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_strict_db_tags(title, db_key, default_tag)
            if tags:
                valid_articles.append({
                    'title': title, 'link': item['link'], 'tags': tags,
                    'date': datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d'),
                    'press': item.get('originallink', '') 
                })

        # 동일 주제 기사 그룹화 (Clustering)
        unique_groups = []
        for art in valid_articles:
            found = False
            for group in unique_groups:
                if get_similarity(art['title'], group[0]['title']) > 0.5:
                    group.append(art); found = True; break
            if not found: unique_groups.append([art])

        # 태그당 최대 12개 출력 (유사 기사는 하나로 합쳐진 상태)
        count = 0
        for group in unique_groups:
            rep = select_representative(group)
            is_min = (db_key != "MNO") and (count < 2)
            if rep['date'] in allowed_dates or is_min:
                if post_notion(db_id, rep['title'], rep['link'], rep['tags'], rep['date']):
                    count += 1
            if count >= 12: break # [태그당 최대 12개 제한]

if __name__ == "__main__":
    # 1. 자회사 (SUBSID)
    collect("SUBSID", [
        (["SK텔링크"], 12, "SK텔링크"),
        (["KT엠모바일"], 12, "KT M모바일"),
        (["LG헬로비전"], 12, "LG헬로비전"),
        (["스카이라이프"], 12, "KT스카이라이프"),
        (["미디어로그", "유모바일"], 12, "미디어로그")
    ], 60)

    # 2. MNO
    collect("MNO", [
        (["통신3사", "이통사"], 12, "통신 3사"),
        (["SK텔레콤", "SKT"], 12, "SKT"),
        (["KT"], 12, "KT"),
        (["LG유플러스"], 12, "LG U+")
    ], 7)

    # 3. 금융 (FIN)
    collect("FIN", [(["토스모바일", "리브모바일", "우리원모바일"], 12, "금융권")], 60)

    # 4. 중소회사 (SMALL)
    collect("SMALL", [(["알뜰폰"], 12, "중소 알뜰폰")], 60)
