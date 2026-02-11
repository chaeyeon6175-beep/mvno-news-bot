import os, requests, re
from datetime import datetime, timedelta
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
    """기존 데이터 삭제"""
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_article_info(url):
    """기사 본문 분석 및 요약 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        content = ""
        # 본문 영역을 찾기 위한 다양한 태그 시도
        for selector in ['div#articleBodyContents', 'div#articleBody', 'article', 'div.content', 'div#news_body']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        if not content:
            content = " ".join([p.get_text(strip=True) for p in soup.find_all('p')])

        # 가독성을 위해 본문 길이 필터링 (80자 미만은 제외)
        if len(content) < 80:
            return None

        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        
        # 소제목 추출 (100자 요약)
        summary = content[:100].replace("\n", " ").strip() + "..."
        return {"img": img, "summary": summary}
    except:
        return None

def is_recent(pub_date_str):
    """최근 5일 이내 기사 허용 (기사가 적을 때를 대비해 2일에서 5일로 완화)"""
    try:
        pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S +0900')
        return pub_date >= datetime.now() - timedelta(days=5)
    except:
        return False

def get_exclusive_keywords(title):
    """중복 방지를 위한 핵심 키워드 추출"""
    clean_title = re.sub(r'[^\w\s]', ' ', title)
    return [w for w in clean_title.split() if len(w) >= 3]

def is_duplicate_topic(new_title, global_seen_keywords):
    """인물명(3글자)이나 핵심단어(4글자)가 겹치면 중복으로 간주"""
    new_words = get_exclusive_keywords(new_title)
    for word in new_words:
        if word in global_seen_keywords:
            return True
    return False

def post_notion(db_id, title, link, img, summary, tag):
    """노션에 데이터 업로드"""
    clean_date = datetime.now().strftime('%Y-%m-%d')
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"date": {"start": clean_date}},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_keywords):
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    # 정확도를 위해 관련도 순(sim)으로 검색
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        print(f"\n▶ [{tag_name}] 키워드 검색 결과 {len(items)}건 분석 시작")
        
        for item in items:
            if count >= limit: break
            if not is_recent(item['pub_date'] if 'pub_date' in item else item.get('pubDate')): continue
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            # 필터링: 링크 중복 및 키워드(홍범식 등) 중복
            if link in global_seen_links: continue
            if is_duplicate_topic(title, global_seen_keywords): continue
            
            # 본문 분석
            article_data = get_article_info(link)
            if not article_data: continue

            # 전송 및 키워드 등록
            post_notion(db_id, title, link, article_data['img'], article_data['summary'], tag_name)
            global_seen_links.add(link)
            global_seen_keywords.update(get_exclusive_keywords(title))
            count += 1
            print(f"   ({count}/{limit}) 수집 성공: {title[:20]}...")
    else:
        print(f"   X API 오류: {res.status_code}")

if __name__ == "__main__":
    # 1. DB 비우기
    for d_id in DB_IDS.values():
        if d_id: clear_database(d_id)
    
    global_seen_links = set()
    global_seen_keywords = set()

    # 2. 실행 설정
    configs = [
        (["통신 3사", "통신3사", "이통3사"], 10, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 10, DB_IDS["MNO"], "SKT"),
        (["KT", "케이티"], 10, DB_IDS["MNO"], "KT"),
        (["LG유플러스", "LGU+"], 10, DB_IDS["MNO"], "LGU+"),
        (["SK텔링크", "세븐모바일"], 10, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 10, DB_IDS["SUBSID"], "KT M모바일"),
        (["KT스카이라이프"], 10, DB_IDS["SUBSID"], "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 10, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 10, DB_IDS["SUBSID"], "미디어로그"),
        (["KB리브모바일", "리브엠"], 10, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 10, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 10, DB_IDS["FIN"], "우리원모바일"),
        (["아이즈모바일"], 10, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 10, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 10, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 10, DB_IDS["SMALL"], "인스모바일")
    ]

    for qs, lim, d_id, tag in configs:
        if d_id: collect_news(qs, lim, d_id, tag, global_seen_links, global_seen_keywords)
