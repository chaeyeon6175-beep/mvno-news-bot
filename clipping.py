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

def validate_link(url):
    """링크가 정상인지 확인. 문제 있으면 None 반환 (소제목 추출 기능 제거)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=5, allow_redirects=True)
        if res.status_code != 200 or "잘못된 경로" in res.text or "존재하지 않는" in res.text:
            return None
        
        soup = BeautifulSoup(res.text, 'html.parser')
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        return img
    except:
        return None

def post_notion(db_id, title, link, img, tag):
    """노션 전송 (소제목 항목 제거 버전)"""
    target_id = clean_id(db_id)
    if not target_id: return False
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": datetime.now().strftime('%Y-%m-%d')}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def collect_news(db_key, configs, processed_links, processed_titles):
    db_id = DB_IDS.get(db_key)
    if not db_id: return

    # 해당 DB 그룹의 모든 키워드를 합쳐서 네이버 검색 (한 번에 많이 가져옴)
    all_keywords = []
    for keywords, _, tag in configs:
        all_keywords.extend(keywords)
    
    search_query = " | ".join([f"\"{k}\"" for k in all_keywords])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        
        # 각 태그(기업)별로 수집된 개수를 추적하기 위한 사전
        tag_counts = {cfg[2]: 0 for cfg in configs}
        
        for item in items:
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else (item['originallink'] or item['link'])
            
            # 1. 제목 중복 검사
            if any(is_similar(title, prev_title) for prev_title in processed_titles):
                continue

            # 2. 정밀 분류 로직: 제목에 특정 기업 키워드가 포함되어 있는지 확인
            matched_tag = None
            for keywords, limit, tag in configs:
                # 해당 태그의 수집 제한량을 넘지 않았는지 확인
                if tag_counts[tag] >= limit:
                    continue
                
                # 제목에 키워드 중 하나라도 포함되어 있는지 검사 (대소문자 무시)
                if any(k.lower() in title.lower() for k in keywords):
                    matched_tag = tag
                    break
            
            # 매칭된 태그가 없으면(제목에 기업명이 없으면) 버림
            if not matched_tag:
                continue

            # 3. 링크 유효성 검증
            img = validate_link(link)
            if not img:
                continue
            
            # 4. 노션 전송
            if post_notion(db_id, title, link, img, matched_tag):
                processed_links.add(link)
                processed_titles.add(title)
                tag_counts[matched_tag] += 1
                print(f"      ✅ [{matched_tag}] 성공: {title[:20]}...")
                time.sleep(0.1)

if __name__ == "__main__":
    links, titles = set(), set()
    
    # [설정] (키워드 리스트, 목표 수집 개수, 태그명)
    mno_configs = [
        (["SK텔레콤", "SKT"], 3, "SKT"),
        (["KT", "케이티"], 3, "KT"),
        (["LG유플러스", "LGU+"], 3, "LG U+"),
        (["통신 3사", "이통3사"], 2, "통신 3사")
    ]
    subsid_configs = [
        (["SK텔링크", "세븐모바일", "7모바일"], 3, "SK텔링크"),
        (["KT M모바일", "KT엠모바일", "케이티엠모바일"], 3, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 3, "LG헬로비전"),
        (["미디어로그", "유모바일", "U모바일"], 3, "미디어로그")
    ]
    fin_configs = [
        (["KB리브모바일", "리브엠", "국민은행 알뜰폰"], 3, "KB 리브모바일"),
        (["토스모바일", "toss mobile"], 3, "토스모바일"),
        (["우리원모바일"], 3, "우리원모바일")
    ]
    small_configs = [
        (["아이즈모바일", "eyesmobile"], 2, "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 2, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 2, "에넥스텔레콤"),
        (["인스모바일"], 2, "인스모바일")
    ]

    print("🚀 뉴스 수집 및 정밀 분류 시작...")
    collect_news("MNO", mno_configs, links, titles)
    collect_news("SUBSID", subsid_configs, links, titles)
    collect_news("FIN", fin_configs, links, titles)
    collect_news("SMALL", small_configs, links, titles)
