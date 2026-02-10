import os, requests, re
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
    except: return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def get_topic_fingerprint(title):
    """제목에서 2글자 이상의 핵심 단어만 뽑아 집합으로 반환"""
    title = re.sub(r'[^\w\s]', ' ', title)
    return set([w for w in title.split() if len(w) >= 2])

def is_duplicate_topic(new_title, global_seen_topics):
    """기존 수집된 기사들과 핵심 단어가 50% 이상 겹치면 중복 주제로 판단"""
    new_fp = get_topic_fingerprint(new_title)
    if not new_fp: return True
    
    for old_fp in global_seen_topics:
        intersection = new_fp.intersection(old_fp)
        # 유사도 계산: 겹치는 단어 수 / 더 짧은 제목의 단어 수
        similarity = len(intersection) / min(len(new_fp), len(old_fp))
        if similarity >= 0.5: # 50% 이상 겹치면 동일 보도자료로 간주
            return True
    return False

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

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_topics):
    """지정된 개수(limit)만큼만, 그리고 중복되지 않은 주제만 수집"""
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break # 10개가 차면 해당 태그 수집 즉시 중단
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            # [필터 1] 키워드 필수 포함 검사
            clean_t = title.replace(" ", "").lower()
            if not any(q.replace(" ", "").lower() in clean_t for q in queries): continue
            
            # [필터 2] URL 중복 검사
            if link in global_seen_links: continue
            
            # [필터 3] 주제 중복 검사 (보도자료 도배 방지)
            if is_duplicate_topic(title, global_seen_topics): continue
                
            # 모든 필터 통과 시 수집
            global_seen_links.add(link)
            global_seen_topics.append(get_topic_fingerprint(title))
            post_notion(db_id, title, link, get_img(link), tag_name)
            count += 1
    return count

if __name__ == "__main__":
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)

    # 전역 변수: 전체 실행 동안 공유하여 '중복 주제'가 다른 태그에 들어가는 것도 방지
    global_seen_links = set()
    global_seen_topics = []

    # 1. MNO (태그당 10개)
    mno_list = [
        (["통신 3사", "통신3사", "이통3사"], 10, "통신 3사"),
        (["SK텔레콤", "SKT"], 10, "SKT"),
        (["KT", "케이티"], 10, "KT"),
        (["LG유플러스", "LGU+"], 10, "LGU+")
    ]
    for qs, lim, tag in mno_list:
        collect_news(qs, lim, DB_IDS["MNO"], tag, global_seen_links, global_seen_topics)

    # 2. MVNO 자회사 (태그당 8~10개)
    sub_list = [
        (["SK텔링크", "세븐모바일"], 10, "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 10, "KT M모바일"),
        (["KT스카이라이프"], 10, "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, "LG헬로비전"),
        (["미디어로그", "유모바일"], 10, "미디어로그")
    ]
    for qs, lim, tag in sub_list:
        collect_news(qs, lim, DB_IDS["SUBSID"], tag, global_seen_links, global_seen_topics)

    # 3. MVNO 금융 (태그당 10개)
    fin_list = [
        (["KB리브모바일", "리브엠"], 10, "KB 리브모바일"),
        (["토스모바일"], 10, "토스모바일"),
        (["우리원모바일"], 10, "우리원모바일")
    ]
    for qs, lim, tag in fin_list:
        collect_news(qs, lim, DB_IDS["FIN"], tag, global_seen_links, global_seen_topics)

    # 4. 중소사업자 (태그당 10개)
    small_list = [
        (["아이즈모바일"], 10, "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 10, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 10, "에넥스텔레콤"),
        (["인스모바일"], 10, "인스모바일")
    ]
    for qs, lim, tag in small_list:
        collect_news(qs, lim, DB_IDS["SMALL"], tag, global_seen_links, global_seen_topics)
