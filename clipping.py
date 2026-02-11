import os, requests, re, time
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
from difflib import SequenceMatcher

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

def is_similar(title1, title2):
    """제목 유사도 70% 이상이거나 8글자 연속 중복 시 필터링"""
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    ratio = SequenceMatcher(None, t1, t2).ratio()
    match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
    return ratio > 0.7 or match.size >= 8

def validate_and_get_info(url):
    """링크가 정상인지 확인하고 정보를 가져옴. 문제 있으면 None 반환"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        # 1. 페이지 접속 확인 (타임아웃 5초)
        res = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        
        # 상태 코드가 200(정상)이 아니거나, '잘못된 경로' 등의 텍스트가 포함된 경우 제외
        if res.status_code != 200 or "잘못된 경로" in res.text or "존재하지 않는" in res.text:
            return None

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 2. 소제목 추출 (보강된 로직)
        sub_title = ""
        for selector in ['div.sub_title', 'strong.sub_title', 'h3.sub_title', 'div.article_summary', 'p.summary', 'div#dic_area b']:
            target = soup.select_one(selector)
            if target and target.get_text(strip=True):
                sub_title = target.get_text(strip=True)
                break
        
        if not sub_title:
            # 소제목 없을 시 본문 요약
            target = soup.select_one('div#dic_area, div#articleBodyContents, div#articleBody, article')
            if target:
                sub_title = ". ".join(re.split(r'\. ', target.get_text(" ", strip=True))[:2])[:150] + "..."

        # 3. 이미지 확인
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        
        return {"img": img, "summary": sub_title or "요약 정보 없음"}
    except:
        return None

def post_notion(db_id, title, link, img, summary, tag):
    target_id = clean_id(db_id)
    if not target_id: return False
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"rich_text": [{"text": {"content": datetime.now().strftime('%Y-%m-%d')}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def collect_news(queries, limit, db_id, tag_name, processed_links, processed_titles):
    if not db_id: return
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        print(f"\n▶ [{tag_name}] 검증 및 수집")
        items = res.json().get('items', [])
        count = 0
        for item in items:
            if count >= limit: break
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 중복 검사 (제목 유사도 기반)
            if any(is_similar(title, prev_title) for prev_title in processed_titles):
                continue
            
            # 링크 결정: 네이버 뉴스 링크가 가장 안전하므로 우선 확인
            link = item['link'] if 'naver.com' in item['link'] else (item['originallink'] or item['link'])
            
            # [핵심] 링크 유효성 검증 및 정보 추출
            info = validate_and_get_info(link)
            if not info: # 링크가 없거나 잘못된 경로면 아예 무시
                continue
            
            if post_notion(db_id, title, link, info['img'], info['summary'], tag_name):
                processed_links.add(link)
                processed_titles.add(title)
                print(f"      ✅ 성공: {title[:15]}...")
                count += 1
                time.sleep(0.2) # 노션 API 속도 제한 준수

if __name__ == "__main__":
    links, titles = set(), set()
    configs = [
        # MNO
        (["통신 3사", "이통3사"], 3, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 3, DB_IDS["MNO"], "SKT"),
        (["KT"], 3, DB_IDS["MNO"], "KT"),
        (["LG유플러스"], 3, DB_IDS["MNO"], "LG U+"),
        # SUBSID
        (["SK텔링크", "세븐모바일"], 2, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일"], 2, DB_IDS["SUBSID"], "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 2, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 2, DB_IDS["SUBSID"], "미디어로그"),
        # FIN
        (["KB리브모바일"], 2, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 2, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 2, DB_IDS["FIN"], "우리원모바일"),
        # SMALL
        (["아이즈모바일"], 1, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤"], 1, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤"], 1, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 1, DB_IDS["SMALL"], "인스모바일")
    ]
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag, links, titles)
