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
    """실행 시 기존 데이터베이스의 모든 페이지를 아카이브(삭제) 처리"""
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_img(url):
    """기사 원문에서 썸네일 이미지 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def is_similar(new_title, seen_titles, threshold=0.4):
    """
    자카드 유사도를 활용한 제목 중복 검사
    단어의 40% 이상이 겹치면 유사한 기사로 판단하여 제외
    """
    if not seen_titles:
        return False
        
    new_words = set(new_title.replace('[', ' ').replace(']', ' ').split())
    
    for seen_title in seen_titles:
        seen_words = set(seen_title.replace('[', ' ').replace(']', ' ').split())
        
        intersection = new_words.intersection(seen_words)
        union = new_words.union(seen_words)
        
        if not union: continue
        similarity = len(intersection) / len(union)
        
        if similarity > threshold:
            return True
    return False

def post_notion(db_id, title, link, img, tag):
    """노션 데이터베이스에 뉴스 페이지 생성"""
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link},
        "분류": {"multi_select": [{"name": tag}]}
    }
    data = {
        "parent": {"database_id": db_id}, 
        "cover": {"type": "external", "external": {"url": img}}, 
        "properties": props
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, global_seen_links):
    """뉴스를 수집하고 유사도 및 키워드 포함 여부 검사"""
    count = 0
    current_tag_titles = [] # 해당 태그 내 유사도 비교용
    
    # OR 검색 쿼리 생성
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            # [검증 1] 제목에 키워드 필수 포함 여부 (공백 제거 후 비교)
            clean_title = title.replace(" ", "").lower()
            if not any(q.replace(" ", "").lower() in clean_title for q in queries):
                continue
            
            # [검증 2] URL 기반 전체 중복 체크
            if link in global_seen_links:
                continue
            
            # [검증 3] 제목 유사도 검사 (태그 내 중복 내용 방지)
            if is_similar(title, current_tag_titles):
                continue
                
            # 모든 검증 통과 시 수집
            global_seen_links.add(link)
            current_tag_titles.append(title)
            
            img = get_img(link)
            post_notion(db_id, title, link, img, tag_name)
            count += 1
    return count

if __name__ == "__main__":
    # 1. 모든 DB 초기화 (전날 기사 삭제)
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)

    # 전역 중복 체크 (URL 기준)
    global_seen_links = set()

    # 2. MNO 시장 수집 (통합 기사 우선 수집으로 분류 정확도 향상)
    collect_news(["통신 3사", "통신3사", "이통3사", "이통 3사"], 10, DB_IDS["MNO"], "통신 3사", global_seen_links)
    collect_news(["SK텔레콤", "SKT"], 10, DB_IDS["MNO"], "SKT", global_seen_links)
    collect_news(["KT", "케이티"], 10, DB_IDS["MNO"], "KT", global_seen_links)
    collect_news(["LG유플러스", "LGU+", "LG U+"], 10, DB_IDS["MNO"], "LGU+", global_seen_links)

    # 3. MVNO 자회사 수집
    sub_tasks = [
        (["SK텔링크", "세븐모바일"], 10, "SK텔링크"),
        (["KT M모바일", "KT엠모바일", "KTM모바일"], 10, "KT M모바일"),
        (["KT스카이라이프", "스카이라이프모바일"], 10, "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, "LG헬로비전"),
        (["미디어로그", "U+유모바일", "유모바일"], 10, "미디어로그")
    ]
    for qs, lim, tag in sub_tasks:
        collect_news(qs, lim, DB_IDS["SUBSID"], tag, global_seen_links)

    # 4. MVNO 금융 수집
    fin_tasks = [
        (["KB리브모바일", "리브엠"], 10, "KB 리브모바일"),
        (["토스모바일"], 10, "토스모바일"),
        (["우리원모바일"], 10, "우리원모바일")
    ]
    for qs, lim, tag in fin_tasks:
        collect_news(qs, lim, DB_IDS["FIN"], tag, global_seen_links)

    # 5. 중소사업자 수집
    small_tasks = [
        (["아이즈모바일"], 10, "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 10, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 10, "에넥스텔레콤"),
        (["인스모바일"], 10, "인스모바일")
    ]
    for qs, lim, tag in small_tasks:
        collect_news(qs, lim, DB_IDS["SMALL"], tag, global_seen_links)

    print(f"Update Finished: {datetime.now()}")
