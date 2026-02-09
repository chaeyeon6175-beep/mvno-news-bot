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
    """기존 뉴스 삭제"""
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

def post_notion(db_id, title, link, date_str, img, tag):
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link},
        "분류": {"multi_select": [{"name": tag}]}
    }
    data = {"parent": {"database_id": db_id}, "cover": {"type": "external", "external": {"url": img}}, "properties": props}
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(query, limit, db_id, tag_name, seen_titles):
    """특정 키워드로 뉴스 수집 (중복 제거 및 엄격한 제목 필터링)"""
    count = 0
    # 검색 정확도를 위해 쌍따옴표 사용
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query=\"{query}\"&display=50&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 필터 1: 제목에 검색어가 실제로 포함되어 있는지 (잡다한 뉴스 배제)
            if query.replace("\"", "") not in title:
                continue
                
            # 필터 2: 전체 DB 통합 중복 제목 체크
            short_title = title[:20]
            if short_title not in seen_titles:
                seen_titles.add(short_title)
                img = get_img(item['originallink'] or item['link'])
                post_notion(db_id, title, item['originallink'] or item['link'], item['pubDate'], img, tag_name)
                count += 1
            
            if count >= limit:
                break
    return count

if __name__ == "__main__":
    # 0. 모든 DB 비우기
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)

    global_seen_titles = set()

    # 1. MNO 시장 (각 10개씩, 총 40개)
    print("MNO 뉴스 수집 중...")
    mno_tasks = [
        ("통신 3사", 10, "통신 3사"), # 이통3사, 통신3사 등 통합 검색용
        ("SK텔레콤", 10, "SKT"),
        ("KT", 10, "KT"),
        ("LG유플러스", 10, "LGU+")
    ]
    for q, lim, tag in mno_tasks:
        collect_news(q, lim, DB_IDS["MNO"], tag, global_seen_titles)

    # 2. MVNO 자회사 (각 8개씩)
    print("자회사 뉴스 수집 중...")
    sub_tasks = ["SK텔링크", "KT M모바일", "KT스카이라이프", "LG헬로비전", "미디어로그"]
    for kw in sub_tasks:
        collect_news(kw, 8, DB_IDS["SUBSID"], kw, global_seen_titles)

    # 3. MVNO 금융 (각 8개씩)
    print("금융 뉴스 수집 중...")
    fin_tasks = ["KB 리브모바일", "토스모바일", "우리원모바일"]
    for kw in fin_tasks:
        collect_news(kw, 8, DB_IDS["FIN"], kw, global_seen_titles)

    # 4. 중소사업자 (주요 사업자 위주)
    print("중소사업자 뉴스 수집 중...")
    small_tasks = ["아이즈모바일", "프리텔레콤", "에넥스텔레콤", "인스모바일"]
    for kw in small_tasks:
        collect_news(kw, 8, DB_IDS["SMALL"], kw, global_seen_titles)

    print("모든 뉴스 업데이트가 완료되었습니다.")
