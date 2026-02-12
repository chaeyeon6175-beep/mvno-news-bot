import os, requests, re, time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 1. 환경 변수 설정
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

def get_similarity(a, b):
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def is_telecom_news(title):
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    if not is_telecom_news(title): return None
    t = title.lower().replace(' ', '')
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None

    # MNO DB 분류 (타 카테고리 기사 철저 배제)
    if db_key == "MNO":
        others = ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "토스", "우리원"]
        if any(x in t for x in others): return None
        
        sa3_kws = ["통신3사", "이통3사", "통신업계", "통신주", "이통사공통", "3사"]
        skt, kt, lg = "skt" in t or "sk텔레콤" in t, "kt" in t or "케이티" in t, "lgu+" in t or "lg유플러스" in t
        
        if any(x in t for x in sa3_kws) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]

    # 2,3,4번 DB 맵 (기존 로직 유지)
    maps = {
        "SUBSID": {"SK텔링크": ["sk텔링크", "7모바일"], "KT M모바일": ["ktm모바일", "kt엠모바일"], "LG헬로비전": ["lg헬로비전", "헬로모바일"], "KT스카이라이프": ["스카이라이프"], "미디어로그": ["미디어로그", "유모바일"]},
        "FIN": {"토스모바일": ["토스모바일", "토스"], "우리원모바일": ["우리원모바일", "우리원"], "KB리브모바일": ["리브모바일", "리브m"]},
        "SMALL": {"아이즈모바일": ["아이즈모바일"], "프리모바일": ["프리텔레콤", "프리티"], "에넥스텔레콤": ["에넥스텔레콤", "a모바일"], "유니컴즈": ["유니컴즈", "모비스트"], "인스코비": ["인스코비"], "세종텔레콤": ["세종텔레콤", "스노우맨"], "큰사람": ["큰사람", "이야기모바일"]}
    }
    if db_key in maps:
        for name, kws in maps[db_key].items():
            if any(k in t for k in kws): return [{"name": name}]
    return None

def post_notion(db_id, title, link, tags, pub_date):
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    data = {
        "parent": {"database_id": target_id},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]}, # 하이퍼링크 적용
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": tags}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def collect_mno(days=7):
    """[개선] 1번 DB 전용: 중복 절대 차단 및 1주일 제한"""
    db_id = DB_IDS.get("MNO")
    # 1주일(7일) 이내 날짜 리스트 생성
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    # 1번 DB 전체 수집 과정에서 공유되는 중복 체크셋
    mno_seen_urls = set()
    mno_seen_titles = []
    mno_tag_counts = {"통신 3사": 0, "SKT": 0, "KT": 0, "LG U+": 0}

    configs = [
        (["통신3사", "통신업계"], "통신 3사"),
        (["SK텔레콤", "SKT"], "SKT"),
        (["KT", "케이티"], "KT"),
        (["LG유플러스", "LGU+"], "LG U+")
    ]

    for keywords, target_tag in configs:
        query = " ".join(keywords)
        raw_items = []
        for sort in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))

        # 검색 결과 내 중복 제거
        unique_items = []
        _tmp = set()
        for i in raw_items:
            if i['link'] not in _tmp: unique_items.append(i); _tmp.add(i['link'])

        for item in unique_items:
            if mno_tag_counts[target_tag] >= 12: break
            if item['link'] in mno_seen_urls: continue # 1번 DB 전체에서 중복 체크

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            if any(get_similarity(title, st) > 0.45 for st in mno_seen_titles): continue

            tags = get_final_tags(title, "MNO", target_tag)
            if tags and tags[0]['name'] == target_tag:
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                
                # [개선] MNO는 무조건 1주일 이내 기사만 (최소 수량 예외 없음)
                if p_date in allowed_dates:
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        mno_seen_urls.add(item['link'])
                        mno_seen_titles.append(title)
                        mno_tag_counts[target_tag] += 1
        print(f"✅ MNO - {target_tag}: {mno_tag_counts[target_tag]}개 완료")

def collect_others(db_key, configs, days):
    """2,3,4번 DB용 기존 로직 (건드리지 않음)"""
    db_id = DB_IDS.get(db_key)
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    for keywords, limit, default_tag in configs:
        tag_count = 0
        seen_urls = set()
        query = " ".join(keywords)
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        if res.status_code != 200: continue
        
        for item in res.json().get('items', []):
            if tag_count >= 12: break
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_final_tags(title, db_key, default_tag)
            if tags:
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                if p_date in allowed_dates or tag_count < 2:
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        tag_count += 1
        print(f"✅ {db_key} - {default_tag}: {tag_count}개 완료")

if __name__ == "__main__":
    # 1. MNO DB: 1주일 제한 및 정밀 중복 제거 적용
    collect_mno(days=7)

    # 2, 3, 4번 DB: 기존 로직 유지
    collect_others("SUBSID", [
        (["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"),
        (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")
    ], 60)
    collect_others("FIN", [(["토스모바일"], 12, "토스모바일"), (["리브모바일"], 12, "KB리브모바일"), (["우리원모바일"], 12, "우리원모바일")], 30)
    collect_others("SMALL", [(["아이즈모바일"], 12, "아이즈모바일"), (["프리텔레콤"], 12, "프리모바일"), (["에넥스텔레콤"], 12, "에넥스텔레콤"), (["유니컴즈"], 12, "유니컴즈"), (["인스코비"], 12, "인스코비"), (["세종텔레콤"], 12, "세종텔레콤"), (["큰사람"], 12, "큰사람")], 60)
