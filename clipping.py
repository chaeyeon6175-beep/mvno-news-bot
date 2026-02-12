import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

# 환경 변수 및 헤더 설정
NAVER_ID, NAVER_SECRET = os.environ.get('NAVER_CLIENT_ID'), os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_IDS = {k: os.environ.get(f'DB_ID_{k}') for k in ["MNO", "SUBSID", "FIN", "SMALL"]}
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def clear_database(db_id):
    """새로운 뉴스를 수집하기 전, 기존에 있는 모든 페이지를 삭제(아카이브)합니다."""
    db_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    if not db_id: return
    
    # 1. DB 내 모든 페이지 ID 조회
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(url, headers=HEADERS)
    if res.status_code == 200:
        pages = res.json().get("results", [])
        for page in pages:
            # 2. 각 페이지 삭제(archived=True)
            page_id = page["id"]
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS, json={"archived": True})
        print(f"🗑️ DB({db_id[:5]}...) 내 기존 뉴스 삭제 완료")

# --- 기존 수집 및 유사도 검사 함수들 (validate_link, is_similar, post_notion 등은 동일) ---
def is_similar(t1, t2):
    s1, s2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', t1), re.sub(r'[^가-힣a-zA-Z0-9]', '', t2)
    return SequenceMatcher(None, s1, s2).ratio() > 0.8

def validate_link(url):
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=h, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1518770660439-4636190af475"
    except: return "https://images.unsplash.com/photo-1518770660439-4636190af475"

def post_notion(db_id, title, link, img, tag, pub_date):
    db_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    return requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data).status_code == 200

def fetch_and_process(db_key, configs, p_titles, days):
    db_id = DB_IDS.get(db_key)
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords])
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=50&sort=sim"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        count = 0
        for item in res.json().get('items', []):
            if count >= limit: break
            p_str = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            if p_str not in allowed_dates: continue
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else item['originallink']
            if any(is_similar(title, pt) for pt in p_titles): continue
            
            img = validate_link(link)
            if post_notion(db_id, title, link, img, tag, p_str):
                p_titles.add(title); count += 1
                print(f"✅ {tag} 수집: {title[:15]}...")

if __name__ == "__main__":
    # 1. 모든 DB 비우기 (기존 뉴스 삭제)
    print("🧹 기존 뉴스 삭제 시작...")
    for key in DB_IDS:
        clear_database(DB_IDS[key])
    
    # 2. 새로운 뉴스 수집 시작
    print("\n🚀 새로운 뉴스 수집 시작...")
    titles = set()
    # MNO/자회사 (5일 범위)
    fetch_and_process("MNO", [(["SKT", "KT", "LGU+"], 10, "통신사")], titles, 5)
    # 금융/중소 (60일 범위)
    fetch_and_process("FIN", [(["리브엠", "토스모바일"], 10, "금융권")], titles, 60)
    # ... (필요한 카테고리 추가)
