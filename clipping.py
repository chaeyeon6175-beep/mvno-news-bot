import os, requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 환경 변수 로드
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID_MNO = os.environ.get('DB_ID_MNO')
DB_ID_SUBSID = os.environ.get('DB_ID_SUBSID')
DB_ID_FIN = os.environ.get('DB_ID_FIN')
DB_ID_SMALL = os.environ.get('DB_ID_SMALL')

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def clear_database(db_id):
    """기존 뉴스 삭제(아카이브)"""
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

def format_date(date_str):
    """네이버 pubDate를 '2026년 02월 09일' 형식으로 변환"""
    try:
        temp_date = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S +0900')
        return temp_date.strftime('%Y년 %m월 %d일')
    except:
        return datetime.now().strftime('%Y년 %m월 %d일')

def post_notion(db_id, title, link, date_str, img, tag=None):
    clean_date = format_date(date_str)
    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link}
    }
    if tag:
        props["분류"] = {"multi_select": [{"name": tag}]}
        
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": props
    }
    return requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def crawl_and_post(kw, db_id, tag=None):
    seen_titles = set()
    final_items = []
    
    # 1. 최신순으로 넉넉히 50개 검색 (오늘 + 어제 기사가 포함되도록)
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={kw}&display=50&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        for item in items:
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            short_title = title[:15] # 중복 방지를 위해 앞 15자 비교
            
            if short_title not in seen_titles:
                seen_titles.add(short_title)
                final_items.append(item)
            
            # 중복 제거 후 10개가 채워지면 중단
            if len(final_items) >= 10:
                break
        
        # 2. 수집된 기사 노션에 전송
        for item in final_items:
            link = item['originallink'] or item['link']
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            img = get_img(link)
            post_notion(db_id, title, link, item['pubDate'], img, tag)
        
        print(f"[{kw}] 총 {len(final_items)}개 기사 업데이트 완료.")

if __name__ == "__main__":
    # 모든 DB 청소 (어제 데이터 삭제)
    for d_id in [DB_ID_MNO, DB_ID_SUBSID, DB_ID_FIN, DB_ID_SMALL]:
        if d_id: clear_database(d_id)

    # 1. MNO 시장
    mno_kws = [("SKT", "SKT"), ("SK텔레콤", "SKT"), ("KT", "KT"), ("LG U+", "LGU+"), ("LG유플러스", "LGU+")]
    for kw, tag in mno_kws:
        crawl_and_post(kw, DB_ID_MNO, tag)

    # 2. MVNO 자회사
    for kw in ["SK텔링크", "KT M모바일", "KT스카이라이프", "LG헬로비전", "미디어로그"]:
        crawl_and_post(kw, DB_ID_SUBSID)

    # 3. MVNO 금융
    for kw in ["KB 리브모바일", "토스모바일", "우리원모바일"]:
        crawl_and_post(kw, DB_ID_FIN)

    # 4. 중소사업자
    for kw in ["아이즈모바일", "프리텔레콤", "에넥스텔레콤"]:
        crawl_and_post(kw, DB_ID_SMALL)
