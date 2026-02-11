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
    """제목의 공백/특수문자를 제거하고 80% 이상 일치하면 중복으로 간주"""
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    return SequenceMatcher(None, t1, t2).ratio() > 0.8

def validate_link(url):
    """링크 유효성 확인 및 이미지 추출 (잘못된 경로 차단)"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200 or any(x in res.text for x in ["잘못된 경로", "존재하지 않는"]):
            return None
        soup = BeautifulSoup(res.text, 'html.parser')
        img_tag = soup.find('meta', property='og:image')
        return img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return None

def post_notion(db_id, title, link, img, tag, pub_date):
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
    t = re.sub(r'\s+', '', title).lower()
    mno_k = ["통신3사", "이통3사", "통신업", "통신사"]
    skt = ["sk텔레콤", "skt"]; kt = ["kt", "케이티"]; lg = ["lg유플러스", "lgu+", "엘지유플러스"]
    if any(k in t for k in mno_k): return "통신 3사"
    h_skt = any(n in t for n in skt); h_kt = any(n in t for n in kt); h_lg = any(n in t for n in lg)
    if h_skt and h_kt and h_lg: return "통신 3사"
    if h_skt and not h_kt and not h_lg: return "SKT"
    if h_kt and not h_skt and not h_lg: return "KT"
    if h_lg and not h_skt and not h_kt: return "LG U+"
    return None

def fetch_and_process(db_key, keywords, limit, tag, p_links, p_titles, days_range):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    
    # 설정된 날짜 범위 리스트
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days_range + 1)]
    
    query = " | ".join([f"\"{k}\"" for k in keywords])
    display_count = 100 if days_range > 10 else 50
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display={display_count}&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        count = 0
        for item in res.json().get('items', []):
            if count >= limit: break
            
            try:
                p_dt = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
                p_str = p_dt.strftime('%Y-%m-%d')
            except: continue

            if p_str not in allowed_dates: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else (item['originallink'] or item['link'])
            
            # [중복 방지 핵심] URL뿐만 아니라 제목 유사도까지 전역으로 체크
            if any(is_similar(title, pt) for pt in p_titles): continue
            if not any(k.lower() in title.lower() for k in keywords): continue
            
            final_tag = classify_mno(title) if db_key == "MNO" else tag
            if not final_tag: continue

            img = validate_link(link)
            if not img: continue
            
            if post_notion(db_id, title, link, img, final_tag, p_str):
                p_links.add(link)
                p_titles.add(title) # 전역 제목 리스트에 추가하여 다음 검색 시 비교
                print(f"   ✅ [{final_tag}] ({p_str}) {title[:15]}...")
                count += 1
                time.sleep(0.1)

if __name__ == "__main__":
    global_links, global_titles = set(), set()
    
    print("🚀 1, 2번 DB 수집 (5일 범위)...")
    mno_tasks = [
        (["통신 3사", "이통 3사"], 5, "통신 3사"),
        (["SK텔레콤", "SKT"], 5, "SKT"),
        (["KT", "케이티"], 5, "KT"),
        (["LG유플러스", "LGU+"], 5, "LG U+")
    ]
    for kws, lim, t in mno_tasks:
        fetch_and_process("MNO", kws, lim, t, global_links, global_titles, 5)

    sub_tasks = [
        (["SK텔링크", "세븐모바일"], 3, "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 3, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 3, "LG헬로비전"),
        (["미디어로그", "유모바일"], 3, "미디어로그")
    ]
    for kws, lim, t in sub_tasks:
        fetch_and_process("SUBSID", kws, lim, t, global_links, global_titles, 5)

    print("\n🚀 3, 4번 DB 수집 (2달 범위 확대)...")
    # 금융/중소 카테고리는 60일 범위로 실행
    fin_tasks = [
        (["KB리브모바일", "리브엠"], 5, "KB 리브모바일"),
        (["토스모바일"], 5, "토스모바일"),
        (["우리원모바일"], 5, "우리원모바일")
    ]
    for kws, lim, t in fin_tasks:
        fetch_and_process("FIN", kws, lim, t, global_links, global_titles, 60)

    small_tasks = [
        (["아이즈모바일"], 3, "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 3, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 3, "에넥스텔레콤"),
        (["인스모바일"], 3, "인스모바일")
    ]
    for kws, lim, t in small_tasks:
        fetch_and_process("SMALL", kws, lim, t, global_links, global_titles, 60)
