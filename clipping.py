import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 설정 로드
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

def post_notion(db_id, title, link, date_str, img, tag=None):
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link}
    }
    # MNO DB일 경우 태그 추가
    if tag:
        props["분류"] = {"multi_select": [{"name": tag}]}
        
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": props
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def crawl_and_post(kw, db_id, tag=None):
    seen = set()
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={kw}&display=20&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    count = 0
    if res.status_code == 200:
        for item in res.json().get('items', []):
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            if title[:15] not in seen:
                seen.add(title[:15])
                img = get_img(item['originallink'] or item['link'])
                post_notion(db_id, title, item['originallink'] or item['link'], item['pubDate'], img, tag)
                count += 1
            if count >= 10: break

if __name__ == "__main__":
    # 1. 모든 DB 청소
    for d_id in [DB_ID_MNO, DB_ID_SUBSID, DB_ID_FIN, DB_ID_SMALL]:
        clear_database(d_id)

    # 2. MNO 시장 (태그 분류 포함)
    mno_kws = [("SKT", "SKT"), ("SK텔레콤", "SKT"), ("KT", "KT"), ("LG U+", "LGU+"), ("LG유플러스", "LGU+")]
    for kw, tag in mno_kws:
        crawl_and_post(kw, DB_ID_MNO, tag)

    # 3. MVNO 자회사
    subsid_kws = ["SK텔링크", "KT M모바일", "KT스카이라이프", "LG헬로비전", "미디어로그"]
    for kw in subsid_kws:
        crawl_and_post(kw, DB_ID_SUBSID)

    # 4. MVNO 금융
    fin_kws = ["KB 리브모바일", "토스모바일", "우리원모바일"]
    for kw in fin_kws:
        crawl_and_post(kw, DB_ID_FIN)

    # 5. 중소사업자 (예시 키워드)
    small_kws = ["아이즈모바일", "프리텔레콤", "에넥스텔레콤"]
    for kw in small_kws:
        crawl_and_post(kw, DB_ID_SMALL)
