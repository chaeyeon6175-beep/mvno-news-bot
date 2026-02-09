import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 1. 환경 변수 로드
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
    """기존 뉴스 삭제 (아카이브 처리)"""
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_img(url):
    """뉴스 기사에서 썸네일 이미지 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def determine_tag(title, default_tag, db_type):
    """기사 제목을 분석하여 최적의 분류 태그 결정"""
    # MNO 특수 로직: 3사가 모두 언급되거나 통합 키워드가 있으면 '통신 3사'로 분류
    if db_type == "MNO":
        combined_keywords = ["통신 3사", "통신3사", "이통3사", "이통 3사", "SKT·KT·LGU+"]
        has_skt = any(x in title for x in ["SKT", "SK텔레콤"])
        has_kt = "KT" in title
        has_lgu = any(x in title for x in ["LGU+", "LG유플러스"])
        
        if any(kw in title for kw in combined_keywords) or (has_skt and has_kt and has_lgu):
            return "통신 3사"
    
    # 키워드별 브랜드명 보정 (제목에 줄임말이 있어도 정식 명칭 태그 부여)
    if "세븐모바일" in title: return "SK텔링크"
    if any(x in title for x in ["M모바일", "엠모바일"]): return "KT M모바일"
    if any(x in title for x in ["유모바일", "미디어로그"]): return "미디어로그"
    if "헬로모바일" in title: return "LG헬로비전"
    if "리브엠" in title: return "KB 리브모바일"
    
    return default_tag

def post_notion(db_id, title, link, img, tag, db_type):
    """노션 데이터베이스에 페이지 생성"""
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    final_tag = determine_tag(title, tag, db_type)

    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link},
        "분류": {"multi_select": [{"name": final_tag}]}
    }
    data = {"parent": {"database_id": db_id}, "cover": {"type": "external", "external": {"url": img}}, "properties": props}
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, seen_titles, db_type):
    """뉴스 검색 및 중복 제거 후 수집"""
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries]) # OR 검색 활용
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 제목 기준 중복 체크 (앞 20자)
            short_title = title[:20]
            if short_title not in seen_titles:
                seen_titles.add(short_title)
                img = get_img(item['originallink'] or item['link'])
                post_notion(db_id, title, item['originallink'] or item['link'], img, tag_name, db_type)
                count += 1
            
            if count >= limit:
                break
    return count

if __name__ == "__main__":
    # 1. 실행 전 기존 DB 비우기
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)

    global_seen_titles = set()

    # 2. MNO 시장 뉴스 수집 (각 태그별 10개씩)
    mno_tasks = [
        (["통신 3사", "이통 3사", "SKT KT LGU+"], 10, "통신 3사"),
        (["SK텔레콤", "SKT"], 10, "SKT"),
        (["KT", "케이티"], 10, "KT"),
        (["LG유플러스", "LGU+", "LG U+"], 10, "LGU+")
    ]
    for qs, lim, tag in mno_tasks:
        collect_news(qs, lim, DB_IDS["MNO"], tag, global_seen_titles, "MNO")

    # 3. MVNO 자회사 뉴스 수집 (각 태그별 8개씩)
    sub_tasks = [
        (["SK텔링크", "세븐모바일", "7모바일"], 8, "SK텔링크"),
        (["KT M모바일", "KT 엠모바일", "KTM모바일"], 8, "KT M모바일"),
        (["KT스카이라이프", "스카이라이프 모바일"], 8, "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 8, "LG헬로비전"),
        (["미디어로그", "U+유모바일", "유모바일"], 8, "미디어로그")
    ]
    for qs, lim, tag in sub_tasks:
        collect_news(qs, lim, DB_IDS["SUBSID"], tag, global_seen_titles, "SUBSID")

    # 4. MVNO 금융 뉴스 수집 (각 태그별 8개씩)
    fin_tasks = [
        (["KB 리브모바일", "리브엠", "국민은행 알뜰폰"], 8, "KB 리브모바일"),
        (["토스모바일", "토스 알뜰폰"], 8, "토스모바일"),
        (["우리원모바일", "우리은행 알뜰폰"], 8, "우리원모바일")
    ]
    for qs, lim, tag in fin_tasks:
        collect_news(qs, lim, DB_IDS["FIN"], tag, global_seen_titles, "FIN")

    # 5. 중소사업자 뉴스 수집 (각 태그별 8개씩)
    small_tasks = [
        (["아이즈모바일", "아이즈비전"], 8, "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 8, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 8, "에넥스텔레콤"),
        (["인스모바일"], 8, "인스모바일")
    ]
    for qs, lim, tag in small_tasks:
        collect_news(qs, lim, DB_IDS["SMALL"], tag, global_seen_titles, "SMALL")

    print(f"완료 시각: {datetime.now()} - 모든 뉴스 업데이트 성공")
