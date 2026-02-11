import os, requests, re
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

def clean_id(raw_id):
    """ID에서 하이픈과 공백을 제거하여 순수 32자리 문자열 반환"""
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def get_article_info(url):
    """뉴스 본문 요약 및 이미지 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        content = ""
        # 주요 언론사 본문 태그 탐색
        for selector in ['div#articleBodyContents', 'div#articleBody', 'article', 'div.content', 'div#news_body']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        
        if not content:
            content = "본문 내용을 가져올 수 없습니다."
            
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        
        # 요약문 정리 (최대 120자)
        summary = content[:120].replace("\n", " ").strip() + "..."
        return {"img": img, "summary": summary}
    except:
        return {
            "img": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000",
            "summary": "뉴스 요약을 불러오는 중 오류가 발생했습니다."
        }

def post_notion(db_id, title, link, img, summary, tag):
    """노션 데이터베이스로 전송 (소제목, 날짜 모두 텍스트 유형 기준)"""
    target_id = clean_id(db_id)
    if not target_id: return
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {
                "title": [{"text": {"content": title, "link": {"url": link}}}]
            },
            "소제목": {
                "rich_text": [{"text": {"content": summary}}]
            },
            "날짜": {
                "rich_text": [{"text": {"content": today_str}}]
            },
            "링크": {
                "url": link
            },
            "분류": {
                "multi_select": [{"name": tag}]
            }
        }
    }
    
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    
    if res.status_code == 200:
        print(f"      ✅ 성공: {title[:20]}...")
    else:
        print(f"      ❌ 실패: {res.json().get('message')}")

def collect_news(queries, limit, db_id, tag_name, processed_links):
    """네이버 뉴스 검색 및 수집"""
    target_id = clean_id(db_id)
    if not target_id:
        print(f"   ⚠️ {tag_name} DB ID가 설정되지 않아 건너뜁니다.")
        return
    
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=30&sort=sim"
    
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        print(f"\n▶ [{tag_name}] 뉴스 수집 시작 (ID: {target_id[:8]}...)")
        items = res.json().get('items', [])
        count = 0
        for item in items:
            if count >= limit: break
            
            link = item['originallink'] or item['link']
            if link in processed_links: continue # 중복 기사 방지
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            info = get_article_info(link)
            
            post_notion(db_id, title, link, info['img'], info['summary'], tag_name)
            processed_links.add(link)
            count += 1
    else:
        print(f"   X 네이버 API 오류: {res.status_code}")

if __name__ == "__main__":
    # 중복 기사 방지용 세트
    processed_links = set()

    # 4개 데이터베이스 전체 수집 설정
    configs = [
        # 1. 통신 3사 (MNO)
        (["SK텔레콤", "KT뉴스", "LG유플러스뉴스"], 5, DB_IDS["MNO"], "통신3사"),
        
        # 2. 자회사 (SUBSID)
        (["SK텔링크", "KT M모바일", "LG헬로비전", "미디어로그"], 5, DB_IDS["SUBSID"], "자회사"),
        
        # 3. 금융권/대형 알뜰폰 (FIN)
        (["KB리브모바일", "토스모바일", "우리원모바일"], 5, DB_IDS["FIN"], "금융권"),
        
        # 4. 중소 알뜰폰 (SMALL)
        (["아이즈모바일", "프리텔레콤", "에넥스텔레콤", "인스모바일"], 5, DB_IDS["SMALL"], "중소알뜰폰")
    ]
    
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag, processed_links)
