import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

# 1. 환경 변수 체크
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
            print(f"🗑️ DB 초기화 완료: {target_id[:5]}... (삭제된 페이지: {len(pages)}개)")
        else:
            print(f"❌ DB 초기화 실패: {res.status_code}")
    except Exception as e:
        print(f"❌ 초기화 에러: {e}")

def post_notion(db_id, title, link, tag, pub_date, desc=""):
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
    if res.status_code != 200:
        print(f"   ㄴ ❌ 노션 전송 실패: {res.status_code} - {res.text[:50]}")
    return res.status_code == 200

def collect(db_key, configs, processed_titles, days):
    db_id = DB_IDS.get(db_key)
    if not db_id:
        print(f"⚠️ {db_key} DB_ID가 설정되지 않았습니다. 패스합니다.")
        return

    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    print(f"\n🔍 {db_key} 수집 시작 (타겟 날짜: {allowed_dates[0]} ~ {allowed_dates[-1]})")

    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords])
        query += " -\"SK쉴더스\" -\"지니뮤직\""
        
        # 네이버 API 호출
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=50&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code != 200:
            print(f"   ㄴ ❌ 네이버 API 호출 실패 ({res.status_code}): {keywords[0]}...")
            continue

        items = res.json().get('items', [])
        print(f"   ㄴ '{keywords[0]}' 검색 결과: {len(items)}개 발견")

        count = 0
        for item in items:
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 필터링 로그 (왜 스킵되는지 확인용)
            if p_date not in allowed_dates and not (db_key in ["FIN", "SMALL"] and count < 2):
                continue
            
            if post_notion(db_id, title, item['link'], tag, p_date, item['description']):
                count += 1
                print(f"      ✅ [{tag}] 등록 성공: {title[:15]}...")
            
            if count >= limit: break
        
        if count == 0:
            print(f"   ㄴ ⚠️ 조건에 맞는 기사가 없어 {tag} 등록을 건너뜁니다.")

if __name__ == "__main__":
    print("🚀 뉴스 클리핑 봇 가동...")
    
    # API 키 로드 여부 확인
    if not NAVER_ID or not NAVER_SECRET:
        print("❌ 에러: 네이버 API 키가 없습니다. Secrets 설정을 확인하세요.")
    else:
        for k in DB_IDS: clear_notion_database(DB_IDS[k])
        
        titles = set()
        collect("SUBSID", [
            (["SK텔링크", "7모바일"], 5, "SK텔링크"),
            (["KT M모바일"], 5, "KT M모바일")
        ], titles, 60)

        collect("MNO", [
            (["SK텔레콤", "SKT"], 15, "SKT"),
            (["KT", "케이티"], 10, "KT"),
            (["LG유플러스"], 10, "LG U+")
        ], titles, 7)

    print("\n🏁 모든 프로세스 완료")
