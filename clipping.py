import os
import requests
from datetime import datetime

# 환경 변수 로드
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_naver_news(keyword):
    # 각 키워드당 10개를 검색해서 그 중 상위 5개를 추출 (중복 대비 여유있게 수집)
    url = f"https://openapi.naver.com/v1/search/news.json?query={keyword}&display=10&sort=sim"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    try:
        res = requests.get(url, headers=headers)
        return res.json().get('items', [])
    except Exception as e:
        print(f"Error: {e}")
        return []

def add_to_notion(title, link, pub_date, keyword_tag):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # 이모지 설정 (키워드에 따라 다르게)
    emoji = "🏢" if "SK텔링크" in keyword_tag else "📰"
    
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "icon": {"emoji": emoji},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "링크": {"url": link},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "분류": {"multi_select": [{"name": keyword_tag}]}
        }
    }
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    search_targets = [
        ("SK텔링크", "SK텔링크"),
        ("텔링크", "SK텔링크"),
        ("알뜰폰 요금제", "요금제현황"),
        ("과기부 알뜰폰 정책", "정부정책"),
        ("MVNO 시장 점유율", "시장동향")
    ]
    
    processed_links = set() # 이번 실행에서 처리된 링크 저장 (중복 방지)
    
    for kw, tag in search_targets:
        news_items = get_naver_news(kw)
        count = 0
        for item in news_items:
            if count >= 5: break # 키워드당 5개까지만
            
            link = item['originallink'] or item['link']
            
            # 1. 이번 실행 내 중복 제거
            if link in processed_links:
                continue
                
            clean_title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
            
            add_to_notion(clean_title, link, item['pubDate'], tag)
            processed_links.add(link)
            count += 1
            print(f"추가됨: {clean_title[:30]}...")
