import os, requests
from datetime import datetime
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
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def determine_mno_tag(title, default_tag):
    """MNO 시장 전용 태그 결정 로직"""
    # 1. '통신 3사' 표현이 있거나, 3사 이름이 모두 포함된 경우 최우선 분류
    mno_names = ["SKT", "SK텔레콤", "KT", "LGU+", "LG유플러스"]
    has_skt = any(x in title for x in ["SKT", "SK텔레콤"])
    has_kt = "KT" in title
    has_lgu = any(x in title for x in ["LGU+", "LG유플러스"])
    
    combined_keywords = ["통신 3사", "통신3사", "이통3사", "이통 3사"]
    
    if any(kw in title for kw in combined_keywords) or (has_skt and has_kt and has_lgu):
        return "통신 3사"
    
    return default_tag

def post_notion(db_id, title, link, img, tag):
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    
    # MNO DB일 경우에만 제목을 다시 검사해서 '통신 3사' 태그 부여
    final_tag = tag
    if db_id == DB_IDS["MNO"]:
        final_tag = determine_mno_tag(title, tag)

    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link},
        "분류": {"multi_select": [{"name": final_tag}]}
    }
    data = {"parent": {"database_id": db_id}, "cover": {"type": "external", "external": {"url": img}}, "properties": props}
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(query, limit, db_id, tag_name, seen_titles):
    count = 0
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query=\"{query}\"&display=50&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 엄격한 필터링: 제목에 키워드가 없으면 제외
            if query.replace("\"", "") not in title:
                continue
                
            short_title = title[:20]
            if short_title not in seen_titles:
                seen_titles.add(short_title)
                img = get_img(item['originallink'] or item['link'])
                post_notion(db_id, title, item['originallink'] or item['link'], img, tag_name)
                count += 1
            
            if count >= limit:
                break
    return count

if __name__ == "__main__":
