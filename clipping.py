import os
import requests
from datetime import datetime

# 환경 변수 로드
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_naver_news(keyword):
    # display=5로 설정하여 각 키워드당 최소 5개씩 가져옵니다.
    url = f"https://openapi.naver.com/v1/search/news.json?query={keyword}&display=5&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    try:
        res = requests.get(url, headers=headers)
        return res.json().get('items', [])
    except Exception as e:
        print(f"Error fetching news for {keyword}: {e}")
        return []

def add_to_notion(title, link, pub_date, keyword_tag):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "icon": {"emoji": "🏢"}, # 기업 관련 뉴스는 빌딩 아이콘
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "링크": {"url": link},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "분류": {"multi_select": [{"name": keyword_tag}]}
        }
    }
    
    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        print(f"성공: {title} [{keyword_tag}]")
    else:
        print(f"실패: {res.status_code}")

if __name__ == "__main__":
    # 검색 대상 리스트 (키워드, 태그이름)
    # SK텔링크와 텔링크를 추가했습니다.
    search_targets = [
        ("SK텔링크", "SK텔링크"),
        ("텔링크", "SK텔링크"),
        ("알뜰폰 요금제", "요금제현황"),
        ("MVNO 점유율", "시장동향")
    ]
    
    for kw, tag in search_targets:
        news_items = get_naver_news(kw)
        for item in news_items:
            clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
            # 노션에 추가
            add_to_notion(clean_title, item['originallink'], item['pubDate'], tag)
