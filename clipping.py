import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 설정 정보 로드
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID = os.environ.get('NOTION_DB_ID')

def get_img(url):
    """기사 원문에서 이미지를 긁어옵니다."""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def post_notion(title, link, date, tag, img):
    """노션에 데이터를 전송합니다."""
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": DB_ID},
        "cover": {"type": "external", "external": {"url": img}}, # 사진 핵심!
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "분류": {"multi_select": [{"name": tag}]},
            "링크": {"url": link},
            "날짜": {"rich_text": [{"text": {"content": date}}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)

if __name__ == "__main__":
    # 검색 키워드와 분류 설정
    targets = [("SK텔링크", "SK텔링크"), ("알뜰폰 요금제", "시장및요금제동향")]
    
    for kw, tag in targets:
        res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={kw}&display=5", 
                           headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code == 200:
            items = res.json().get('items', [])
            for item in items:
                link = item['originallink'] or item['link']
                # 제목에서 HTML 태그 제거
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                img = get_img(link)
                post_notion(title, link, item['pubDate'], tag, img)

    print(f"작업 완료: {datetime.now()}")
