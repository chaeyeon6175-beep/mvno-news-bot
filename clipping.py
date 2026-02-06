import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 설정 정보 로드
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID_SK = os.environ.get('DB_ID_SK')
DB_ID_TREND = os.environ.get('DB_ID_TREND')

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def clear_database(db_id):
    """기존 데이터를 모두 삭제(아카이브)"""
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        pages = res.json().get("results", [])
        for page in pages:
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_img(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def format_date(date_str):
    try:
        temp_date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S +0900')
        return temp_date.strftime('%Y년 %m월 %d일')
    except:
        return datetime.now().strftime('%Y년 %m월 %d일')

def post_notion(db_id, title, link, date_str, img):
    clean_date = format_date(date_str)
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
            "링크": {"url": link}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

if __name__ == "__main__":
    search_tasks = [
        {"kw": "SK텔링크", "target_db": DB_ID_SK},
        {"kw": "알뜰폰 요금제", "target_db": DB_ID_TREND}
    ]
    
    for task in search_tasks:
        clear_database(task['target_db']) # 기존 기사 삭제
        
        # 중복 방지를 위한 세트와 결과 리스트
        seen_titles = set()
        final_items = []
        
        # 중복 제외 15개를 채우기 위해 넉넉히 50개 검색
        res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={task['kw']}&display=50&sort=sim", 
                           headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                # 제목 앞 15자리가 같으면 중복으로 간주 (유사 기사 방지)
                short_title = title[:15]
                
                if short_title not in seen_titles:
                    seen_titles.add(short_title)
                    final_items.append(item
