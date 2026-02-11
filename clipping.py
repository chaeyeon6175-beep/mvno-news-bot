import os, requests, re, time
from datetime import datetime, timedelta
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
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    ratio = SequenceMatcher(None, t1, t2).ratio()
    match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
    return ratio > 0.7 or match.size >= 8

def validate_link(url):
    """링크 유효성 검사 및 이미지 추출"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200 or any(x in res.text for x in ["잘못된 경로", "존재하지 않는"]):
            return None
        soup = BeautifulSoup(res.text, 'html.parser')
        img_tag = soup.find('meta', property='og:image')
        return img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return None

def post_notion(db_id, title, link, img, tag, pub_date):
    """노션 전송 (소제목 제거, 실제 기사 작성일 적용)"""
    target_id = clean_id(db_id)
    if not target_id: return False
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def classify_mno(title):
    """MNO 전용 정밀 분류 로직"""
    title_clean = re.sub(r'\s+', '', title).lower()
    
    # 1. 통신 3사 우선 (키워드 매칭 혹은 3사 이름 동시 등장)
    mno_all = ["통신3사", "이통3사", "통신업"]
    skt_names = ["sk텔레콤", "skt"]
    kt_names = ["kt", "케이티"]
    lg_names = ["lg유플러스", "lgu+", "엘지유플러스"]
    
    if any(k in title_clean for k in mno_all):
        return "통신 3사"
    
    # 제목에 3개 회사 이름이 모두 포함된 경우
    has_skt = any(n in title_clean for n in skt_names)
    has_kt = any(n in title_clean for n in kt_names)
    has_lg = any(n in title_clean for n in lg_names)
    
    if has_skt and has_kt and has_lg:
        return "통신 3사"
    
    # 2. 단일 회사 분류 (딱 하나만 포함되어야 함)
    found = []
    if has_skt: found.append("SKT")
    if has_kt: found.append("KT")
    if has_lg: found.append("LG U+")
    
    if len(found) == 1:
        return found[0]
    
    return None

def collect_news(db_key, configs, processed_links, processed_titles):
    db_id = DB_IDS.get(db_key)
    if not db_id: return

    all_keywords = []
    for keywords, _, _ in configs: all_keywords.extend(keywords)
    
    search_query = " | ".join([f"\"{k}\"" for k in all_keywords])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=100&sort=date"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        tag_counts = {cfg[2]: 0 for cfg in configs}
        
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        allowed_dates = [today.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d')]

        for item in items:
            # 기사 날짜 변환 (RFC822 -> YYYY-MM-DD)
            pub_date_dt = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            pub_date_str = pub_date_dt.strftime('%Y-%m-%d')
            
            # 날짜 필터링 (오늘/어제만)
            if pub_date_str not in allowed_dates: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else (item['originallink'] or item['link'])
            
            if any(is_similar(title, prev_title) for prev_title in processed_titles): continue

            # 분류 로직
            matched_tag = None
            if db_key == "MNO":
                matched_tag = classify_mno(title)
            else:
                for keywords, limit, tag in configs:
                    if tag_counts[tag] >= limit: continue
                    if any(k.lower() in title.lower() for k in keywords):
                        matched_tag = tag
                        break
            
            if not matched_tag: continue
            
            img = validate_link(link)
            if not img: continue
            
            if post_notion(db_id, title, link, img, matched_tag, pub_date_str):
                processed_links.add(link)
                processed_titles.add(title)
                if matched_tag in tag_counts: tag_counts[matched_tag] += 1
                print(f"      ✅ [{matched_tag}] ({pub_date_str}) 성공: {title[:15]}...")
                time.sleep(0.1)

if __name__ == "__main__":
    links, titles = set(), set()
    # MNO는 태그 개수 제한을 위해 전체 limit 설정
    mno_configs = [([], 10, "통신 3사"), ([], 10, "SKT"), ([], 10, "KT"), ([], 10, "LG U+")] 
    # 자회사/금융/중소 로직은 이전과 동일하게 키워드 기반 매칭
    subsid_configs = [
        (["SK텔링크", "세븐모바일", "7모바일"], 3, "SK텔링크"),
        (["KT M모바일", "KT엠모바일", "케이티엠모바일"], 3, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 3, "LG헬로비전"),
        (["미디어로그", "유모바일", "U모바일"], 3, "미디어로그")
    ]
    # ... (생략된 FIN, SMALL 설정은 이전과 동일)

    print("🚀 기사 날짜 기준 정밀 수집 시작...")
    collect_news("MNO", mno_configs, links, titles)
    collect_news("SUBSID", subsid_configs, links, titles)
    # FIN, SMALL은 편의상 생략했으나 collect_news 호출 시 동일하게 작동합니다.
