import os
import requests
from datetime import datetime

# 환경 변수 로드
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_naver_news(keyword):
    # 정렬 방식을 sim(유사도/정확도 순)으로 하여 주요 기사 위주로 수집
    url = f"https://openapi.naver.com/v1/search/news.json?query={keyword}&display=5&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    try:
        res = requests.get(url, headers=headers)
        return res.json().get('items', [])
    except Exception as e:
        print(f"Error fetching news: {e}")
        return []

def add_to_notion(title, link, pub_date, keyword_tag):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # 노션에 전송할 데이터 구조
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "icon": {"emoji": "📰"}, # 모든 페이지에 뉴스 아이콘 부여
        "properties": {
            "제목": {
                "title": [{"text": {"content": title}}]
            },
            "링크": {
                "url": link
            },
            "날짜": {
                "rich_text": [{"text": {"content": pub_date}}]
            },
            "분류": {
                "multi_select": [{"name": keyword_tag}] # 자동으로 태그 생성 및 할당
            }
        }
    }
    
    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 200:
        print(f"성공: {title} [{keyword_tag}]")
    else:
        print(f"실패: {res.status_code} - {res.text}")

if __name__ == "__main__":
    # 검색 키워드와 매칭될 태그 이름 설정
    # (키워드, 태그이름)
    search_targets = [
        ("알뜰폰 요금제", "요금제현황"),
        ("과학기술정보통신부 알뜰폰", "정부정책"),
        ("MVNO 점유율", "시장동향")
    ]
    
    for kw, tag in search_targets:
        news_items = get_naver_news(kw)
        for item in news_items:
            # HTML 태그 제거 및 특수문자 처리
            clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
            add_to_notion(clean_title, item['originallink'], item['pubDate'], tag)
