import os, requests, re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 환경 변수 로드
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_IDS = {
    "MNO": os.environ.get('DB_ID_MNO'),
    "SUBSID": os.environ.get('DB_ID_SUBSID'),
    "FIN": os.environ.get('DB_ID_FIN'),
    "SMALL": os.environ.get('DB_ID_SMALL')
}
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def clean_id(raw_id):
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def post_notion(db_id, title, link, img, summary, tag):
    target_id = clean_id(db_id)
    if not target_id: return
    
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"date": {"start": datetime.now().strftime('%Y-%m-%d')}},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    if res.status_code != 200:
        print(f"      ❌ 전송 실패 (ID: {target_id}): {res.text}")
    else:
        print(f"      ✅ 전송 성공: {title[:15]}...")

def get_article_info(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        content = ""
        for selector in ['div#articleBodyContents', 'div#articleBody', 'article', 'div.content']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        if not content: content = "본문 요약을 가져올 수 없습니다."
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        return {"img": img, "summary": content[:100] + "..."}
    except:
        return {"img": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000", "summary": "요약을 불러오지 못했습니다."}

def collect_news(queries, limit, db_id, tag_name):
    if not db_id: return
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=10&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        print(f"\n▶ [{tag_name}] 분석 시작")
        for item in items[:limit]:
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            info = get_article_info(link)
            post_notion(db_id, title, link, info['img'], info['summary'], tag_name)
    else:
        print(f"   X 네이버 API 오류: {res.status_code}")

if __name__ == "__main__":
    configs = [
        (["SK텔링크", "세븐모바일"], 2, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 2, DB_IDS["SUBSID"], "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 2, DB_IDS["SUBSID"], "LG헬로비전")
    ]
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag)
