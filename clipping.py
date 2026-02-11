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
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def get_article_info(url):
    """기사 본문 길이 체크 및 썸네일, 소제목(첫 문장) 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 본문 텍스트 추출 (주요 언론사 공통 태그 탐색)
        content = ""
        target_tags = ['div#articleBodyContents', 'div#articleBody', 'div.article_body', 'section#articleBody']
        for tag in target_tags:
            found = soup.select_one(tag)
            if found:
                content = found.get_text(strip=True)
                break
        
        # 만약 위 태그로 못찾으면 p 태그들 합침
        if not content:
            content = " ".join([p.get_text(strip=True) for p in soup.find_all('p')])

        # 1. 본문 길이 필터 (너무 짧은 기사 제외 - 약 150자 미만 시 4줄 이내로 간주)
        if len(content) < 150:
            return None

        # 2. 썸네일 이미지
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

        # 3. 소제목(첫 80자 요약)
        summary = content[:80].replace("\n", " ") + "..."
        
        return {"img": img, "summary": summary}
    except:
        return None

def is_recent(pub_date_str):
    """최대 2일 전 기사까지만 허용"""
    try:
        # 네이버 pubDate 예시: Tue, 11 Feb 2026 09:30:00 +0900
        pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S +0900')
        limit_date = datetime.now() - timedelta(days=2)
        return pub_date >= limit_date
    except:
        return False

def get_topic_signature(title):
    clean_title = re.sub(r'[^\w\s]', ' ', title)
    return set([w for w in clean_title.split() if len(w) >= 2])

def is_duplicate_topic(new_title, global_seen_topics):
    new_sig = get_topic_signature(new_title)
    if not new_sig: return True
    for old_sig in global_seen_topics:
        intersection = new_sig.intersection(old_sig)
        if any(len(w) >= 4 for w in intersection): return True
        if len(intersection) >= 3: return True
    return False

def post_notion(db_id, title, link, img, summary, tag):
    clean_date = datetime.now().strftime('%Y-%m-%d')
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]}, # 새로 추가된 속성
            "날짜": {"date": {"start": clean_date}},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, global_seen_links, global_seen_topics):
    count = 0
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    # 검색 결과를 날짜순(sim 아님)으로 가져와서 최신성 보장
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=date"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        for item in res.json().get('items', []):
            if count >= limit: break 
            
            # [필터 1] 날짜 필터 (2일 이내)
            if not is_recent(item['pubDate']): continue
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            if link in global_seen_links: continue
            if is_duplicate_topic(title, global_seen_topics): continue
            
            # [필터 2] 본문 분석 (길이 체크 및 요약 추출)
            article_data = get_article_info(link)
            if not article_data: continue # 본문이 너무 짧거나 접속 불가면 스킵

            # 수집 확정
            global_seen_links.add(link)
            global_seen_topics.append(get_topic_signature(title))
            post_notion(db_id, title, link, article_data['img'], article_data['summary'], tag_name)
            count += 1
    print(f"[{tag_name}] {count}개 수집 완료")

if __name__ == "__main__":
    # DB 초기화 및 실행 로직은 이전과 동일
    # ... (생략된 메인 실행부는 이전 코드와 같으나 post_notion 인자값에 summary 추가)
