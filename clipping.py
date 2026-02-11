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
    """ID에서 하이픈과 공백을 제거"""
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def get_article_info(url):
    """뉴스 본문 요약 및 이미지 추출"""
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        content = ""
        for selector in ['div#articleBodyContents', 'div#articleBody', 'article', 'div.content']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        
        if not content:
            content = "본문 내용을 가져올 수 없습니다."
            
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        
        return {"img": img, "summary": content[:120].replace("\n", " ").strip() + "..."}
    except:
        return {
            "img": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000",
            "summary": "뉴스 요약을 불러오는 중 오류가 발생했습니다."
        }

def post_notion(db_id, title, link, img, summary, tag):
    """노션 데이터베이스로 전송 (소제목, 날짜 모두 텍스트 기준)"""
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
        print(f"      ✅ 전송 성공: {title[:20]}...")
    else:
        print(f"      ❌ 전송 실패: {res.json().get('message')}")

def collect_news(queries, limit, db_id, tag_name):
    """네이버 뉴스 검색 및 수집"""
    if not db_id: return
    
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=20&sort=sim"
    
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        print(f"\n▶ [{tag_name}] 뉴스 수집 시작")
        items = res.json().get('items', [])
        count = 0
        for item in items:
            if count >= limit: break
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['originallink'] or item['link']
            
            # 본문 요약 정보 가져오기
            info = get_article_info(link)
            
            # 노션 전송
            post_notion(db_id, title, link, info['img'], info['summary'], tag_name)
            count += 1
    else:
        print(f"   X 네이버 API 오류: {res.status_code}")

if __name__ == "__main__":
    # 수집 설정 (키워드, 개수, DB ID, 태그)
    configs = [
        (["SK텔링크", "세븐모바일"], 2, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 2, DB_IDS["SUBSID"], "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 2, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 2, DB_IDS["SUBSID"], "미디어로그")
    ]
    
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag)
