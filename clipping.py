import os, requests, re
from datetime import datetime
from bs4 import BeautifulSoup

NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_IDS = {
    "MNO": os.environ.get('DB_ID_MNO'),
    "SUBSID": os.environ.get('DB_ID_SUBSID'),
    "FIN": os.environ.get('DB_ID_FIN'),
    "SMALL": os.environ.get('DB_ID_SMALL')
}
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def clear_database(db_id):
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_img(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except: return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def get_topic_fingerprint(title):
    title = re.sub(r'[^\w\s]', ' ', title)
    return set([w for w in title.split() if len(w) >= 2])

def is_duplicate_topic(new_title, global_seen_topics):
    new_fp = get_topic_fingerprint(new_title)
    if not new_fp: return True
    for old_fp in global_seen_topics:
        intersection = new_fp.intersection(old_fp)
        if not new_fp or not old_fp: continue
        similarity = len(intersection) / min(len(new_fp), len(old_fp))
        if similarity >= 0.5: return True
    return False

def post_notion(db_id, title, link, img, tag):
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_topics):
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break # 10개 도달 시 즉시 중단
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            if not any(q.replace(" ", "").lower() in title.replace(" ", "").lower() for q in queries): continue
            if link in global_seen_links: continue
            if is_duplicate_topic(title, global_seen_topics): continue
                
            global_seen_links.add(link)
            global_seen_topics.append(get_topic_fingerprint(title))
            post_notion(db_id, title, link, get_img(link), tag_name)
            count += 1
    print(f"[{tag_name}] 최종 수집 개수: {count}")

if __name__ == "__main__":
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)
    
    global_seen_links = set()
    global_seen_topics = []

    # 1. MNO (각 10개)
    for qs, lim, tag in [ (["통신 3사", "통신3사", "이통3사"], 10, "통신 3사"), (["SK텔레콤", "SKT"], 10, "SKT"), (["KT", "케이티"], 10, "KT"), (["LG유플러스", "LGU+"], 10, "LGU+") ]:
        collect_news(qs, lim, DB_IDS["MNO"], tag, global_seen_links, global_seen_topics)
    
    # 2. SUBSID (각 10개)
    for qs, lim, tag in [ (["SK텔링크", "세븐모바일"], 10, "SK텔링크"), (["KT M모바일", "KT엠모바일"], 10, "KT M모바일"), (["KT스카이라이프"], 10, "KT스카이라이프"), (["LG헬로비전", "헬로모바일"], 10, "LG헬로비전"), (["미디어로그", "유모바일"], 10, "미디어로그") ]:
        collect_news(qs, lim, DB_IDS["SUBSID"], tag, global_seen_links, global_seen_topics)

    # 3. FIN (각 10개)
    for qs, lim, tag in [ (["KB리브모바일", "리브엠"], 10, "KB 리브모바일"), (["토스모바일"], 10, "토스모바일"), (["우리원모바일"], 10, "우리원모바일") ]:
        collect_news(qs, lim, DB_IDS["FIN"], tag, global_seen_links, global_seen_topics)

    # 4. SMALL (각 10개)
    for qs, lim, tag in [ (["아이즈모바일"], 10, "아이즈모바일"), (["프리텔레콤", "프리모바일"], 10, "프리텔레콤"), (["에넥스텔레콤", "A모바일"], 10, "에넥스텔레콤"), (["인스모바일"], 10, "인스모바일") ]:
        collect_news(qs, lim, DB_IDS["SMALL"], tag, global_seen_links, global_seen_topics)
