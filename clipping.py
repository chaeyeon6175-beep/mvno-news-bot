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
    """네이버 날짜 형식을 '2026년 02월 06일'로 변환"""
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
    
    # 오늘 날짜 (중복 기사 중 오늘 것만 골라내기 위함)
    today_str = datetime.now().strftime('%d %b %Y')
    
    for task in search_tasks:
        clear_database(task['target_db']) # 1. 기존 기사 삭제
        
        seen_titles = set()
        final_items = []
        
        # 2. 최신순(sort=date)으로 넉넉히 50개 검색
        res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={task['kw']}&display=50&sort=date", 
                           headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                # 오늘 기사인지 확인
                if today_str in item['pubDate']:
                    title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                    # 중복 제목 방지 (앞 15자 비교)
                    short_title = title[:15]
                    
                    if short_title not in seen_titles:
                        seen_titles.add(short_title)
                        final_items.append(item)
                    
                    if len(final_items) >= 10: # 10개 채워지면 중단
                        break
            
            # 3. 노션에 업로드
            for item in final_items:
                link = item['originallink'] or item['link']
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                img = get_img(link)
                post_notion(task['target_db'], title, link, item['pubDate'], img)

    print(f"오늘의 뉴스 10개 업데이트 완료: {datetime.now()}")
