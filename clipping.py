import os, requests, re
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

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
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def clean_url(url):
    """중복 체크용으로만 사용하되, 원본 URL의 핵심 파라미터는 보존"""
    parsed = urlparse(url)
    # 기사 식별에 필요한 파라미터가 있을 수 있으므로 path까지만 깔끔하게 정리
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def get_article_info(url):
    """뉴스 본문 및 이미지 추출 (접속 실패 시 안전장치 강화)"""
    try:
        # 네이버 뉴스 링크인 경우와 일반 신문사 링크인 경우 모두 대응
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=8)
        res.encoding = 'utf-8'
        
        if res.status_code != 200:
            return None # 접속 실패 시 None 반환하여 수집 제외

        soup = BeautifulSoup(res.text, 'html.parser')
        content = ""
        # 본문 추출 로직 (더 넓은 범위를 탐색)
        for selector in ['div#articleBodyContents', 'div#dic_area', 'div#articleBody', 'article', 'div.content']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        
        if not content: content = "본문 요약 정보를 가져올 수 없습니다."
        
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        
        return {"img": img, "summary": content[:120].replace("\n", " ").strip() + "..."}
    except:
        return None # 에러 발생 시 수집 제외

def post_notion(db_id, title, link, img, summary, tag):
    target_id = clean_id(db_id)
    if not target_id: return
    today_str = datetime.now().strftime('%Y-%m-%d')
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"rich_text": [{"text": {"content": today_str}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    if res.status_code == 200:
        print(f"      ✅ [{tag}] 전송 성공: {title[:15]}...")
    else:
        print(f"      ❌ 전송 실패: {res.json().get('message')}")

def collect_news(queries, limit, db_id, tag_name, processed_links):
    if not db_id: return
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        count = 0
        for item in items:
            if count >= limit: break
            
            # 1. 링크 결정 (신문사 원문 우선하되, 실패 시 네이버 링크 사용하도록 로직 설계)
            link = item['originallink'] or item['link']
            check_key = clean_url(link)
            
            if check_key in processed_links:
                continue
            
            # 2. 기사 정보 가져오기 (여기서 접속 가능 여부 체크)
            info = get_article_info(link)
            
            # 원문 링크가 깨졌을 경우 네이버 뉴스 링크로 재시도
            if info is None and item['link'] != item['originallink']:
                link = item['link']
                info = get_article_info(link)
            
            # 둘 다 깨졌으면 이 기사는 건너뜀
            if info is None:
                continue
                
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            post_notion(db_id, title, link, info['img'], info['summary'], tag_name)
            
            processed_links.add(check_key)
            count += 1
    else:
        print(f"   X 네이버 API 오류: {res.status_code}")

if __name__ == "__main__":
    global_processed_links = set()
    configs = [
        # 1. MNO
        (["통신 3사", "이통3사"], 5, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 5, DB_IDS["MNO"], "SKT"),
        (["KT", "케이티"], 5, DB_IDS["MNO"], "KT"),
        (["LG유플러스", "LGU+"], 5, DB_IDS["MNO"], "LG U+"),
        # 2. 자회사 (SUBSID)
        (["SK텔링크", "세븐모바일"], 3, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 3, DB_IDS["SUBSID"], "KT M모바일"),
        (["KT스카이라이프"], 3, DB_IDS["SUBSID"], "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 3, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 3, DB_IDS["SUBSID"], "미디어로그"),
        # 3. 금융권 (FIN)
        (["KB리브모바일", "리브엠"], 3, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 3, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 3, DB_IDS["FIN"], "우리원모바일"),
        # 4. 중소 알뜰폰 (SMALL)
        (["아이즈모바일"], 2, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 2, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 2, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 2, DB_IDS["SMALL"], "인스모바일")
    ]
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag, global_processed_links)
