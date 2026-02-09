import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 환경 변수 설정
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
    """실행 시 기존 DB 내용 삭제"""
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

def post_notion(db_id, title, link, img, tag):
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link},
        "분류": {"multi_select": [{"name": tag}]}
    }
    data = {"parent": {"database_id": db_id}, "cover": {"type": "external", "external": {"url": img}}, "properties": props}
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, seen_titles):
    """지정한 태그(tag_name)별로 최대 limit 개수만큼만 수집"""
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break # 해당 태그의 할당량을 채우면 즉시 중단
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # [대전제] 제목에 키워드가 반드시 포함되어야 함 (공백 무시 검사)
            clean_title = title.replace(" ", "").lower()
            if not any(q.replace(" ", "").lower() in clean_title for q in queries):
                continue
            
            # 전체 중복 체크
            short_title = title[:20]
            if short_title not in seen_titles:
                seen_titles.add(short_title)
                img = get_img(item['originallink'] or item['link'])
                post_notion(db_id, title, item['originallink'] or item['link'], img, tag_name)
                count += 1
    return count

if __name__ == "__main__":
    # 1. 모든 DB 초기화
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)

    global_seen_titles = set()

    # 2. MNO 시장 (태그별 최대 10개)
    mno_tasks = [
        (["통신 3사", "통신3사", "이통3사", "이통 3사"], 10, "통신 3사"),
        (["SK텔레콤", "SKT"], 10, "SKT"),
        (["KT", "케이티"], 10, "KT"),
        (["LG유플러스", "LGU+", "LG U+"], 10, "LGU+")
    ]
    for qs, lim, tag in mno_tasks:
        collect_news(qs, lim, DB_IDS["MNO"], tag, global_seen_titles)

    # 3. MVNO 자회사 (태그별 최대 10개)
    sub_tasks = [
        (["SK텔링크", "세븐모바일"], 10, "SK텔링크"),
        (["KT M모바일", "KT엠모바일", "KTM모바일"], 10, "KT M모바일"),
        (["KT스카이라이프", "스카이라이프모바일"], 10, "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, "LG헬로비전"),
        (["미디어로그", "U+유모바일", "유모바일"], 10, "미디어로그")
    ]
    for qs, lim, tag in sub_tasks:
        collect_news(qs, lim, DB_IDS["SUBSID"], tag, global_seen_titles)

    # 4. MVNO 금융 (태그별 최대 10개)
    fin_tasks = [
        (["KB리브모바일", "리브엠"], 10, "KB 리브모바일"),
        (["토스모바일"], 10, "토스모바일"),
        (["우리원모바일"], 10, "우리원모바일")
    ]
    for qs, lim, tag in fin_tasks:
        collect_news(qs, lim, DB_IDS["FIN"], tag, global_seen_titles)

    # 5. 중소사업자 (태그별 최대 10개)
    small_tasks = [
        (["아이즈모바일"], 10, "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 10, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 10, "에넥스텔레콤"),
        (["인스모바일"], 10, "인스모바일")
    ]
    for qs, lim, tag in small_tasks:
        collect_news(qs, lim, DB_IDS["SMALL"], tag, global_seen_titles)
