import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup # 기사 이미지를 찾기 위한 도구

# 1. 환경 변수 설정
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_article_image(url):
    """기사 원문 링크에서 대표 이미지(og:image) 주소를 추출합니다."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 대부분의 뉴스 사이트는 og:image라는 태그에 대표 사진을 담아둡니다.
        img_tag = soup.find('meta', property='og:image')
        if img_tag:
            return img_tag['content']
    except:
        pass
    # 사진을 못 찾으면 나올 기본 배경 (세련된 비즈니스 이미지)
    return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

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

def add_to_notion(title, link, pub_date, keyword_tag, desc, img_url):
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "cover": {"type": "external", "external": {"url": img_url}}, # 긁어온 실제 기사 이미지 적용
        "icon": {"emoji": "📰"},
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
        ("알뜰폰 요금제", "요금제현황"),
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
            
            # 여기서 실제 기사 페이지의 이미지를 가져옵니다.
            actual_img_url = get_article_image(link)
            
            add_to_notion(clean_title, link, item['pubDate'], tag, clean_desc, actual_img_url)
            processed_links.add(link)
            count += 1

    print(f"--- 이미지 포함 수집 완료: {datetime.now()} ---")
