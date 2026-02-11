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
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def clear_database(db_id):
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_article_info(url):
    """기사 본문 길이 체크 및 썸네일, 소제목 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        content = ""
        target_tags = ['div#articleBodyContents', 'div#articleBody', 'div.article_body', 'section#articleBody']
        for tag in target_tags:
            found = soup.select_one(tag)
            if found:
                content = found.get_text(strip=True)
                break
        if not content:
            content = " ".join([p.get_text(strip=True) for p in soup.find_all('p')])

        # 필터: 본문 150자 미만(약 4줄 이내)은 버림
        if len(content) < 150: return None

        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        summary = content[:100].replace("\n", " ") + "..." # 소제목용 100자 추출
        
        return {"img": img, "summary": summary}
    except: return None

def is_recent(pub_date_str):
    """최대 2일 전(48시간) 기사까지만 허용"""
    try:
        # 네이버 pubDate: Tue, 11 Feb 2026 09:30:00 +0900
        pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S +0900')
        return pub_date >= datetime.now() - timedelta(days=2)
    except: return False

def get_exclusive_keywords(title):
    clean_title = re.sub(r'[^\w\s]', ' ', title)
    return [w for w in clean_title.split() if len(w) >= 3]

def is_duplicate_topic(new_title, global_seen_keywords):
    new_words = get_exclusive_keywords(new_title)
    for word in new_words:
        if word in global_seen_keywords: return True
    # 4글자 이상 단어 포함 여부도 체크
    clean_title = re.sub(r'[^\w\s]', ' ', new_title)
    for w in clean_title.split():
        if len(w) >= 4 and any(w in existing for existing in global_seen_keywords): return True
    return False

def post_notion(db_id, title, link, img, summary, tag):
    clean_date = datetime.now().strftime('%Y-%m-%d')
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]}, # 노션에 '소제목' 속성 필수
            "날짜": {"date": {"start": clean_date}},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_keywords):
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=date"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break
            if not is_recent(item['pubDate']): continue
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            if link in global_seen_links or is_duplicate_topic(title, global_seen_keywords): continue
            
            article_data = get_article_info(link)
            if not article_data: continue

            global_seen_links.add(link)
            global_seen_keywords.update(get_exclusive_keywords(title))
            post_notion(db_id, title, link, article_data['img'], article_data['summary'], tag_name)
            count += 1
    print(f"[{tag_name}] 수집 완료: {count}개")

if __name__ == "__main__":
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)
    
    global_seen_links = set()
    global_seen_keywords = set()

    # 실행 설정 (각 태그당 최대 10개)
    configs = [
        (["통신 3사", "통신3사", "이통3사"], 10, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 10, DB_IDS["MNO"], "SKT"),
        (["KT", "케이티"], 10, DB_IDS["MNO"], "KT"),
        (["LG유플러스", "LGU+"], 10, DB_IDS["MNO"], "LGU+"),
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
