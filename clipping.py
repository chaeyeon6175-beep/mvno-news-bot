import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup

NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
NOTION_DB_ID = os.environ.get('NOTION_DB_ID')

def get_article_image(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img_tag = soup.find('meta', property='og:image')
        return img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def add_to_notion(title, link, pub_date, keyword_tag, desc, img_url):
    url = "https://api.notion.com/v1/pages"
    headers = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    
    data = {
        "parent": {"database_id": NOTION_DB_ID},
        "cover": {"type": "external", "external": {"url": img_url}}, # 갤러리 사진 핵심
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "요약": {"rich_text": [{"text": {"content": desc}}]},
            "분류": {"multi_select": [{"name": keyword_tag}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link} # 별도 링크 속성 추가
        }
    }
    requests.post(url, headers=headers, json=data)

if __name__ == "__main__":
    search_targets = [("SK텔링크", "SK텔링크"), ("알뜰폰", "요금제현황")]
    for kw, tag in search_targets:
        res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={kw}&display=5", 
                           headers={"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET})
        for item in res.json().get('items', []):
            link = item['originallink'] or item['link']
            clean_title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            clean_desc = item['description'].replace('<b>','').replace('</b>','').replace('&quot;','"')[:100]
            img_url = get_article_image(link)
            add_to_notion(clean_title, link, item['pubDate'], tag, clean_desc, img_url)
