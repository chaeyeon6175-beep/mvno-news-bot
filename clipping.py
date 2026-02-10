import os, requests, re
from datetime import datetime
from bs4 import BeautifulSoup

# [환경 변수 로드 부분은 이전과 동일]
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

def get_topic_fingerprint(title):
    """제목에서 핵심 키워드만 뽑아 '지문(Fingerprint)'을 생성"""
    # 1. 특수문자 제거
    title = re.sub(r'[^\w\s]', ' ', title)
    # 2. 2글자 이상의 명사성 단어만 추출 (조사, 접속사 제거 효과)
    words = [w for w in title.split() if len(w) >= 2]
    # 3. 정렬된 집합으로 반환 (순서가 바뀌어도 동일하게 인식하기 위함)
    return set(words)

def is_same_topic(new_title, seen_topics):
    """기존 수집된 기사들과 주제가 겹치는지 검사"""
    new_fingerprint = get_topic_fingerprint(new_title)
    if not new_fingerprint: return False

    for old_fingerprint in seen_topics:
        # 두 제목 간의 공통 단어 추출
        intersection = new_fingerprint.intersection(old_fingerprint)
        # 유사도 계산 (공통 단어 개수 / 짧은 쪽 제목의 전체 단어 수)
        # 비율이 60% 이상이면 사실상 같은 보도자료로 판단
        similarity = len(intersection) / min(len(new_fingerprint), len(old_fingerprint))
        
        if similarity >= 0.6: # 유사도 기준값 (0.6 = 60%)
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
    count = 0
    
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            # [필터 1] 키워드 필수 포함 검사
            clean_title_no_space = title.replace(" ", "").lower()
            if not any(q.replace(" ", "").lower() in clean_title_no_space for q in queries):
                continue
            
            # [필터 2] URL 중복 검사
            if link in global_seen_links:
                continue
            
            # [필터 3] 주제(Topic) 중복 검사 - 보도자료 도배 방지 핵심
            if is_same_topic(title, global_seen_topics):
                continue
                
            # 수집 확정
            global_seen_links.add(link)
            global_seen_topics.append(get_topic_fingerprint(title))
            
            img = get_img(link)
            post_notion(db_id, title, link, img, tag_name)
            count += 1
    return count

if __name__ == "__main__":
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)

    global_seen_links = set()
    global_seen_topics = [] # 수집된 기사들의 키워드 뭉치를 저장

    # MNO (통합 3사 -> 개별사 순으로 수집하여 중복 제거 극대화)
    collect_news(["통신 3사", "통신3사", "이통3사", "이통 3사"], 10, DB_IDS["MNO"], "통신 3사", global_seen_links, global_seen_topics)
    collect_news(["SK텔레콤", "SKT"], 10, DB_IDS["MNO"], "SKT", global_seen_links, global_seen_topics)
    collect_news(["KT", "케이티"], 10, DB_IDS["MNO"], "KT", global_seen_links, global_seen_topics)
    collect_news(["LG유플러스", "LGU+", "LG U+"], 10, DB_IDS["MNO"], "LGU+", global_seen_links, global_seen_topics)

    # MVNO 자회사
    sub_tasks = [
        (["SK텔링크", "세븐모바일"], 10, "SK텔링크"),
        (["KT M모바일", "KT엠모바일", "KTM모바일"], 10, "KT M모바일"),
        (["KT스카이라이프", "스카이라이프모바일"], 10, "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, "LG헬로비전"),
        (["미디어로그", "U+유모바일", "유모바일"], 10, "미디어로그")
    ]
    for qs, lim, tag in sub_tasks:
        collect_news(qs, lim, DB_IDS["SUBSID"], tag, global_seen_links, global_seen_topics)

    # MVNO 금융 / 중소사업자 등 이하 동일 방식으로 진행...
    # (코드 중복을 위해 이하 생략하지만, 실제 적용시에는 위 task들과 동일하게 global_seen_topics를 인자로 전달해야 합니다.)
