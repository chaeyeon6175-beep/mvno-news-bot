import os
import requests
from datetime import datetime

# 1. 환경 변수 로드 (GitHub Secrets에 등록된 정보)
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_naver_news(keyword):
    """네이버 뉴스 API를 통해 키워드 검색 결과를 가져옵니다."""
    url = f"https://openapi.naver.com/v1/search/news.json?query={keyword}&display=10&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    try:
        res = requests.get(url, headers=headers)
        return res.json().get('items', [])
    except:
        return []

def add_to_notion(title, link, pub_date, keyword_tag, desc):
    """노션 데이터베이스에 새로운 페이지(뉴스 카드)를 생성합니다."""
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # 전략: 키워드별로 다른 커버 이미지를 삽입하여 갤러리 뷰 가독성 향상
    if "SK텔링크" in keyword_tag:
        # SK텔링크 관련 비즈니스 이미지 (Unsplash)
        img_url = "https://images.unsplash.com/photo-1573163281530-5be9c2960d37?q=80&w=2069&auto=format&fit=crop"
        emoji = "🏢"
    elif "요금제" in keyword_tag:
        # 요금제/금융 관련 이미지
        img_url = "https://images.unsplash.com/photo-1554224155-6726b3ff858f?q=80&w=2011&auto=format&fit=crop"
        emoji = "💰"
    else:
        # 일반 뉴스 이미지
        img_url = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=2070&auto=format&fit=crop"
        emoji = "📰"
    
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "cover": {"type": "external", "external": {"url": img_url}}, # 갤러리 이미지용 커버
        "icon": {"emoji": emoji},
        "properties": {
            "제목": {
                "title": [{"text": {"content": title, "link": {"url": link}}}] # 제목 클릭 시 기사 이동
            },
            "요약": {
                "rich_text": [{"text": {"content": desc}}]
            },
            "분류": {
                "multi_select": [{"name": keyword_tag}]
            },
            "날짜": {
                "rich_text": [{"text": {"content": pub_date}}]
            }
        }
    }
    requests.post(url, headers=headers
