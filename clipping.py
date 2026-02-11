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
    """ID에서 공백, 하이픈 등을 제거하여 순수 32자리 문자열로 반환"""
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def clear_database(db_id):
    target_id = clean_id(db_id)
    query_url = f"https://api.notion.com/v1/databases/{target_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_article_info(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        content = ""
        for selector in ['div#articleBodyContents', 'div#articleBody', 'article', 'div.content', 'div#news_body']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        if not content:
            content = " ".join([p.get_text(strip=True) for p in soup.find_all('p')])
        if len(content) < 80: return None
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        summary = content[:100].replace("\n", " ").strip() + "..."
        return {"img": img, "summary": summary}
    except: return None

def post_notion(db_id, title, link, img, summary, tag):
    target_db_id = clean_id(db_id)
    clean_date = datetime.now().strftime('%Y-%m-%d')
    data = {
        "parent": {"database_id": target_db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"date": {"start": clean_date}},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    if res.status_code != 200:
        print(f"      ❌ 전송 실패 ({res.status_code}): {res.text}")
    else:
        print(f"      ✅ 전송 완료")

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_keywords):
    if not db_id: return
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        print(f"\n▶ [{tag_name}] 분석 시작")
        for item in items:
            if count >= limit: break
            pub_date_str = item.get('pubDate') or item.get('pub_date')
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S +0900')
                if pub_date < datetime.now() - timedelta(days=5): continue
            except: continue
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            if link in global_seen_links: continue
            
            article_data = get_article_info(link)
            if not article_data: continue

            print(f"   ({count+1}/{limit}) 시도: {title[:20]}...")
            post_notion(db_id, title, link, article_data['img'], article_data['summary'], tag_name)
            global_seen_links.add(link)
            count += 1
    else:
        print(f"   X API 오류: {res.status_code}")

if __name__ == "__main__":
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)
    
    global_seen_links = set()
    global_seen_keywords = set()

    configs = [
        (["통신 3사", "통신3사", "이통3사"], 10, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 10, DB_IDS["MNO"], "SKT"),
        (["KT", "케이티"], 10, DB_IDS["MNO"], "KT"),
        (["LG유플러스", "LGU+"], 10, DB_IDS["MNO"], "LG U+"),
        (["SK텔링크", "세븐모바일"], 10, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 10, DB_IDS["SUBSID"], "KT M모바일"),
        (["KT스카이라이프"], 10, DB_IDS["SUBSID"], "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 10, DB_IDS["SUBSID"], "미디어로그"),
        (["KB리브모바일", "리브엠"], 10, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 10, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 10, DB_IDS["FIN"], "우리원모바일"),
        (["아이즈모바일"], 10, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 10, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 10, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 10, DB_IDS["SMALL"], "인스모바일")
    ]

    for qs, lim, d_id, tag in configs:
        if d_id: collect_news(qs, lim, d_id, tag, global_seen_links, global_seen_keywords)
