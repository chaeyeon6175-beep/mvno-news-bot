import os
import requests
from datetime import datetime

# 1. 환경 변수 로드
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
    try:
        res = requests.get(url, headers=headers)
        return res.json().get('items', [])
    except:
        return []

def add_to_notion(title, link, pub_date, keyword_tag, desc):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    if "SK텔링크" in keyword_tag:
        img_url = "https://images.unsplash.com/photo-1573163281530-5be9c2960d37?q=80&w=2069&auto=format&fit=crop"
        emoji = "🏢"
    elif "요금제" in keyword_tag:
        img_url = "https://images.unsplash.com/photo-1554224155-6726b3ff858f?q=80&w=2011&auto=format&fit=crop"
        emoji = "💰"
    else:
        img_url = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=2070&auto=format&fit=crop"
        emoji = "📰"
    
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "cover": {"type": "external", "external": {"url": img_url}},
        "icon": {"emoji": emoji},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "요약": {"rich_text": [{"text": {"content": desc}}]},
            "분류": {"multi_select": [{"name": keyword_tag}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]}
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
    
    processed_links = set()
    
    for kw, tag in search_targets:
        news_items = get_naver_news(kw)
        count = 0
        for item in news_items:
            if count >= 5: break
            link = item['originallink'] or item['link']
            if link in processed_links: continue
            
            clean_title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            clean_desc = item['description'].replace('<b>','').replace('</b>','').replace('&quot;','"')[:150] + "..."
            
            add_to_notion(clean_title, link, item['pubDate'], tag, clean_desc)
            processed_links.add(link)
            count += 1

    print(f"--- 작업 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
