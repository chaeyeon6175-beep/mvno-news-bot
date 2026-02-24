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

def clear_database(db_id):
    """수집 전 기존 기사 삭제"""
    print(f"🧹 데이터베이스 비우기: {db_id}")
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    while True:
        res = requests.post(query_url, headers=HEADERS)
        results = res.json().get("results", [])
        if not results: break
        for page in results:
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
        if not res.json().get("has_more"): break

def get_similarity(a, b):
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a); b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def is_telecom_news(title):
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "주가", "증시", "상장"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "출시"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    if not is_telecom_news(title): return None
    t = title.lower().replace(' ', '')
    if db_key == "MNO":
        sa3_kws = ["통신3사", "이통3사", "통신업계", "3사"]
        skt, kt, lg = "skt" in t or "sk텔레콤" in t, "kt" in t or "케이티" in t, "lgu+" in t or "lg유플러스" in t
        if any(x in t for x in sa3_kws) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]
    maps = {
        "SUBSID": {"SK텔링크": ["sk텔링크", "7모바일"], "KT M모바일": ["ktm모바일", "kt엠모바일"], "LG헬로비전": ["lg헬로비전", "헬로모바일"], "KT스카이라이프": ["스카이라이프"], "미디어로그": ["미디어로그", "유모바일"]},
        "FIN": {"토스모바일": ["토스모바일", "토스"], "우리원모바일": ["우리원모바일", "우리원"], "KB리브모바일": ["리브모바일", "리브m", "kb국민"]},
        "SMALL": {"아이즈모바일": ["아이즈모바일"], "프리모바일": ["프리텔레콤", "프리티"], "에넥스텔레콤": ["에넥스텔레콤", "a모바일"], "유니컴즈": ["유니컴즈", "모비스트"], "인스코비": ["인스코비"], "세종텔레콤": ["세종텔레콤", "스노우맨"], "큰사람": ["큰사람", "이야기모바일"]}
    }
    if db_key in maps:
        for name, kws in maps[db_key].items():
            if any(k in t for k in kws): return [{"name": name}]
    return None

def post_notion(db_id, title, link, tags, pub_date):
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    data = {"parent": {"database_id": target_id}, "properties": {"제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]}, "날짜": {"rich_text": [{"text": {"content": pub_date}}]}, "링크": {"url": link}, "분류": {"multi_select": tags}}}
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def collect_news(db_key, configs, default_days=7):
    """통합 수집 로직: 분류별 최소 5개, 최대 15개"""
    db_id = DB_IDS.get(db_key)
    clear_database(db_id)
    
    seen_urls, seen_titles = set(), []
    # 7일(MNO용) 또는 60일(알뜰폰용) 날짜 리스트 생성
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(default_days + 1)]

    for keywords, _, target_tag in configs:
        tag_count = 0
        print(f"📡 {db_key} - {target_tag} 수집 중...")
        
        for sort in ["sim", "date"]:
            if tag_count >= 15: break
            query = " ".join(keywords)
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code != 200: continue

            for item in res.json().get('items', []):
                if tag_count >= 15: break
                if item['link'] in seen_urls: continue
                
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                if any(get_similarity(title, st) > 0.45 for st in seen_titles): continue

                tags = get_final_tags(title, db_key, target_tag)
                if tags and tags[0]['name'] == target_tag:
                    p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                    
                    # [로직] 7일 이내 기사거나, 혹은 아직 최소 5개를 못 채웠다면 과거 기사라도 수집
                    if p_date in allowed_dates or tag_count < 5:
                        if post_notion(db_id, title, item['link'], tags, p_date):
                            seen_urls.add(item['link'])
                            seen_titles.append(title)
                            tag_count += 1
        print(f"✅ {target_tag}: {tag_count}개 수집됨")

if __name__ == "__main__":
    # 1. MNO (기본 7일 기준)
    collect_news("MNO", [
        (["SK텔레콤", "SKT"], 15, "SKT"), (["KT", "케이티"], 15, "KT"),
        (["LG유플러스", "LGU+"], 15, "LG U+"), (["통신3사", "통신업계"], 15, "통신 3사")
    ], 7)

    # 2. SUBSID (기본 60일 기준)
    collect_news("SUBSID", [
        (["SK텔링크"], 15, "SK텔링크"), (["KT엠모바일"], 15, "KT M모바일"),
        (["LG헬로비전"], 15, "LG헬로비전"), (["스카이라이프"], 15, "KT스카이라이프"), (["미디어로그"], 15, "미디어로그")
    ], 60)

    # 3. FIN (기본 30일 기준)
    collect_news("FIN", [
        (["토스모바일"], 15, "토스모바일"), (["리브모바일"], 15, "KB리브모바일"), (["우리원모바일"], 15, "우리원모바일")
    ], 30)

    # 4. SMALL (기본 60일 기준)
    collect_news("SMALL", [
        (["아이즈모바일"], 15, "아이즈모바일"), (["프리텔레콤"], 15, "프리모바일"), (["에넥스텔레콤"], 15, "에넥스텔레콤"), 
        (["유니컴즈"], 15, "유니컴즈"), (["인스코비"], 15, "인스코비"), (["세종텔레콤"], 15, "세종텔레콤"), (["큰사람"], 15, "큰사람")
    ], 60)
