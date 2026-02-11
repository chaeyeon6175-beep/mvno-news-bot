import os, requests, re
from datetime import datetime
from bs4 import BeautifulSoup

# [환경 변수 로드 부분은 동일]
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

def get_exclusive_keywords(title):
    """제목에서 중복을 방지할 '독점 키워드' 추출"""
    clean_title = re.sub(r'[^\w\s]', ' ', title)
    words = clean_title.split()
    
    # 3글자 이상의 단어들(인물명, 기업명, 핵심 명사)을 추출
    # 예: '홍범식', '영업이익', '흑자전환', '해킹여파' 등
    return [w for w in words if len(w) >= 3]

def is_duplicate_topic(new_title, seen_keywords):
    """제목에 이미 수집된 '독점 키워드'가 하나라도 포함되어 있는지 확인"""
    new_words = get_exclusive_keywords(new_title)
    
    for word in new_words:
        # 이전에 수집된 기사의 핵심 단어 중 현재 제목에 포함된 것이 있다면 중복!
        if word in seen_keywords:
            return True
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

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_keywords):
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break 
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            # [기본 필터]
            if not any(q.replace(" ", "").lower() in title.replace(" ", "").lower() for q in queries): continue
            if link in global_seen_links: continue
            
            # [핵심 필터] 주제 독점 방지 (인물명, 핵심 단어 중복 체크)
            if is_duplicate_topic(title, global_seen_keywords):
                continue
                
            # 수집 확정 시, 해당 기사의 모든 3글자 이상 단어를 '금지어' 리스트에 추가
            global_seen_links.add(link)
            global_seen_keywords.update(get_exclusive_keywords(title)) 
            
            post_notion(db_id, title, link, get_img(link), tag_name)
            count += 1
    print(f"[{tag_name}] 최종 수집: {count}개")

if __name__ == "__main__":
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)
    
    global_seen_links = set()
    global_seen_keywords = set() # 수집된 기사들의 모든 핵심 단어 저장소

    # 각 섹션별 실행 (순서대로 10개씩 엄격 제한)
    configs = [
        # MNO
        (["통신 3사", "통신3사", "이통3사"], 10, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 10, DB_IDS["MNO"], "SKT"),
        (["KT", "케이티"], 10, DB_IDS["MNO"], "KT"),
        (["LG유플러스", "LGU+"], 10, DB_IDS["MNO"], "LGU+"),
        # SUBSID
        (["SK텔링크", "세븐모바일"], 10, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 10, DB_IDS["SUBSID"], "KT M모바일"),
        (["KT스카이라이프"], 10, DB_IDS["SUBSID"], "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 10, DB_IDS["SUBSID"], "미디어로그"),
        # FIN
        (["KB리브모바일", "리브엠"], 10, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 10, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 10, DB_IDS["FIN"], "우리원모바일"),
        # SMALL
        (["아이즈모바일"], 10, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 10, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 10, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 10, DB_IDS["SMALL"], "인스모바일")
    ]

    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag, global_seen_links, global_seen_keywords)
