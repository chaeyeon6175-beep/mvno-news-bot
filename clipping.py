import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 1. 환경 변수 로드
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

def clear_notion_database(db_id):
    if not db_id: return
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            pages = res.json().get("results", [])
            for page in pages:
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
            print(f"🗑️ DB 초기화 완료: {target_id[:5]}")
    except: pass

def post_notion(db_id, title, link, tag, pub_date):
    if not db_id: return False
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    data = {
        "parent": {"database_id": target_id},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def collect(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    print(f"\n🔍 {db_key} 수집 시작 (날짜 범위: {allowed_dates[-1]} ~ {allowed_dates[0]})")

    for keywords, limit, tag in configs:
        # [수정] 따옴표를 제거하여 검색 유연성 확보
        query = " ".join(keywords) 
        
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=sim" # 관련도순으로 우선 변경
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code != 200:
            print(f"   ❌ API 에러: {res.status_code}")
            continue

        items = res.json().get('items', [])
        print(f"   ㄴ '{tag}' 검색어 '{query}' -> {len(items)}개 발견")

        count = 0
        for item in items:
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 날짜 필터 (금융/중소는 최소 2개 보장)
            if p_date in allowed_dates or (db_key in ["FIN", "SMALL"] and count < 2):
                if post_notion(db_id, title, item['link'], tag, p_date):
                    count += 1
                    print(f"      ✅ 등록: {title[:20]}...")
            
            if count >= limit: break
        
        if count == 0:
            print(f"   ⚠️ '{tag}' 조건에 맞는 최신 기사가 없습니다.")

if __name__ == "__main__":
    # API 키 확인
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 네이버 API 키 누락")
    else:
        for k in DB_IDS: clear_notion_database(DB_IDS[k])
        
        # 1. SUBSID (60일)
        collect("SUBSID", [
            (["SK텔링크"], 10, "SK텔링크"),
            (["KT M모바일"], 5, "KT M모바일")
        ], 60)

        # 2. MNO (7일) - SKT 10개 이상 목표
        collect("MNO", [
            (["SK텔레콤", "SKT"], 15, "SKT"),
            (["KT"], 10, "KT"),
            (["LG유플러스"], 10, "LG U+")
        ], 7)

        # 3. FIN/SMALL (60일)
        collect("FIN", [(["리브모바일", "토스모바일"], 5, "금융권")], 60)
        collect("SMALL", [(["알뜰폰 뉴스"], 5, "중소 알뜰폰")], 60)

    print("\n🏁 작업 완료")
