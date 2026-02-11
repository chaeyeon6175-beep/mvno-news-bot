import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
from difflib import SequenceMatcher

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

def clean_id(raw_id):
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def is_similar(title1, title2):
    """제목 유사도 검사 (중복 방지)"""
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    ratio = SequenceMatcher(None, t1, t2).ratio()
    match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
    return ratio > 0.7 or match.size >= 8

def validate_link(url):
    """링크가 정상인지 확인하고 이미지 경로 반환"""
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
    """노션 전송 (소제목 제거, 기사 작성일 적용)"""
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
    """MNO 정밀 분류 (통신3사 우선, 단일 회사 차선)"""
    title_clean = re.sub(r'\s+', '', title).lower()
    mno_keywords = ["통신3사", "이통3사", "통신업", "통신사"]
    skt_names = ["sk텔레콤", "skt"]
    kt_names = ["kt", "케이티"]
    lg_names = ["lg유플러스", "lgu+", "엘지유플러스"]
    
    # 1. '통신 3사'로 분류해야 하는 경우
    if any(k in title_clean for k in mno_keywords): return "통신 3사"
    
    has_skt = any(n in title_clean for n in skt_names)
    has_kt = any(n in title_clean for n in kt_names)
    has_lg = any(n in title_clean for n in lg_names)
    
    if has_skt and has_kt and has_lg: return "통신 3사"
    
    # 2. 딱 한 회사만 언급된 경우
    found = []
    if has_skt: found.append("SKT")
    if has_kt: found.append("KT")
    if has_lg: found.append("LG U+")
    
    if len(found) == 1: return found[0]
    return None

def collect_news(db_key, configs, processed_links, processed_titles):
    db_id = DB_IDS.get(db_key)
    if not db_id: return

    # 오늘 기준 5일 전까지의 날짜 리스트 생성
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, 6)]
    
    # 검색어 최적화 (MNO는 대표 검색어로 넓게 검색)
    search_keywords = []
    if db_key == "MNO":
        search_keywords = ["SK텔레콤", "KT", "LG유플러스", "통신 3사"]
    else:
        for keywords, _, _ in configs: search_keywords.extend(keywords)
    
    query = " | ".join([f"\"{k}\"" for k in search_keywords])
    # 날짜 범위가 넓으므로 수집량을 100개로 확대
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        tag_counts = {cfg[2]: 0 for cfg in configs}
        
        for item in items:
            pub_date_dt = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            pub_date_str = pub_date_dt.strftime('%Y-%m-%d')
            
            # 5일 전 ~ 어제 기사만 수집
            if pub_date_str not in allowed_dates: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else (item['originallink'] or item['link'])
            
            if any(is_similar(title, prev_title) for prev_title in processed_titles): continue

            # 분류 로직 적용
            matched_tag = None
            if db_key == "MNO":
                matched_tag = classify_mno(title)
            else:
                for keywords, limit, tag in configs:
                    if tag_counts[tag] >= limit: continue
                    if any(k.lower() in title.lower() for k in keywords):
                        matched_tag = tag; break
            
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
    # MNO 설정
    mno_cfg = [([], 5, "통신 3사"), ([], 5, "SKT"), ([], 5, "KT"), ([], 5, "LG U+")]
    # 자회사 설정
    sub_cfg = [
        (["SK텔링크", "세븐모바일", "7모바일"], 4, "SK텔링크"),
        (["KT M모바일", "KT엠모바일", "케이티엠모바일"], 4, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 4, "LG헬로비전"),
        (["미디어로그", "유모바일", "U모바일"], 4, "미디어로그")
    ]
    # 금융권 및 중소 설정 (동일 방식)
    fin_cfg = [(["KB리브모바일", "리브엠"], 3, "KB 리브모바일"), (["토스모바일"], 3, "토스모바일"), (["우리원모바일"], 3, "우리원모바일")]
    small_cfg = [(["아이즈모바일"], 2, "아이즈모바일"), (["프리텔레콤"], 2, "프리텔레콤"), (["에넥스텔레콤", "A모바일"], 2, "에넥스텔레콤"), (["인스모바일"], 2, "인스모바일")]

    print("🚀 5일치 기사 수집 및 정밀 분류 시작...")
    collect_news("MNO", mno_cfg, links, titles)
    collect_news("SUBSID", sub_cfg, links, titles)
    collect_news("FIN", fin_cfg, links, titles)
    collect_news("SMALL", small_cfg, links, titles)
