import os
import requests
from datetime import datetime

# 환경 변수 로드 (Github Actions에서 설정할 예정)
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_naver_news(keyword):
    url = f"https://openapi.naver.com/v1/search/news.json?query={keyword}&display=10&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    res = requests.get(url, headers=headers)
    return res.json().get('items', [])

def add_to_notion(title, link, pub_date):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "링크": {"url": link},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]}
        }
    }
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    keywords = ["알뜰폰 시장", "MVNO 현안"]
    for kw in keywords:
        news_items = get_naver_news(kw)
        for item in news_items:
            # HTML 태그 제거 및 데이터 전송
            clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"')
            add_to_notion(clean_title, item['originallink'], item['pubDate'])
            print(f"Added: {clean_title}")
