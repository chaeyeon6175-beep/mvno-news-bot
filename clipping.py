import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 설정 정보 로드
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID_SK = os.environ.get('DB_ID_SK')
DB_ID_TREND = os.environ.get('DB_ID_TREND')

def get_img(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def format_date(date_str):
    """네이버 날짜 형식을 '2024년 05월 20일' 형식으로 변환"""
    try:
        # 네이버 pubDate: 'Mon, 20 May 2024 10:00:00 +0900'
        temp_date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S +0900')
        return temp_date.strftime('%Y년 %m월 %d일')
    except:
        return datetime.now().strftime('%Y년 %m월 %d일')

def post_notion(db_id, title, link, date_str, img):
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    clean_date = format_date(date_str)
    
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {
                "title": [
                    {
                        "text": {
                            "content": title,
                            "link": {"url": link} # 제목 자체에 하이퍼링크 삽입
                        }
                    }
                ]
            },
            "날짜": {"rich_text": [{"text": {"content": clean_date}}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)

if __name__ == "__main__":
    search_tasks = [
        {"kw": "SK텔링크", "target_db": DB_ID_SK},
        {"kw": "알뜰폰 요금제", "target_db": DB_ID_TREND}
    ]
    
    for task in search_tasks:
        res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={task['kw']}&display=8", 
                           headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                link = item['originallink'] or item['link']
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                img = get_img(link)
                post_notion(task['target_db'], title, link, item['pubDate'], img)

    print(f"작업 완료: {datetime.now()}")
