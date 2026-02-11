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
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    return SequenceMatcher(None, t1, t2).ratio() > 0.8 # 유사도 기준 살짝 완화

def validate_link(url):
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
    
    has_skt = any(n in t for n in skt)
    has_kt = any(n in t for n in kt)
    has_lg = any(n in t for n in lg)
    
    if has_skt and has_kt and has_lg: return "통신 3사"
    if has_skt and not has_kt and not has_lg: return "SKT"
    if has_kt and not has_skt and not has_lg: return "KT"
    if has_lg and not celebrated_skt and not has_kt: return "LG U+" # 오타수정 celebrated -> has
    if has_lg and not has_skt and not has_kt: return "LG U+"
    return None

def fetch_and_process(db_key, keywords, limit, tag, p_links, p_titles):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    
    # 오늘 포함 6일치 (0~5일 전)
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6)]
    
    query = " | ".join([f"\"{k}\"" for k in keywords])
    url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=50&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        count = 0
        for item in res.json().get('items', []):
            if count >= limit: break
            
            p_dt = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900')
            p_str = p_dt.strftime('%Y-%m-%d')
            if p_str not in allowed_dates: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else (item['originallink'] or item['link'])
            
            if any(is_similar(title, pt) for pt in p_titles): continue

            # 제목 키워드 매칭 확인
            if not any(k.lower() in title.lower() for k in keywords): continue
            
            # MNO는 별도 분류 로직 태움
            final_tag = classify_mno(title) if db_key == "MNO" else tag
            if not final_tag: continue

            img = validate_link(link)
            if not img: continue
            
            if post_notion(db_id, title, link, img, final_tag, p_str):
                p_links.add(link); p_titles.add(title)
                print(f"   ✅ [{final_tag}] {title[:15]}...")
                count += 1
                time.sleep(0.1)

if __name__ == "__main__":
    p_links, p_titles = set(), set()
    
    # 1. MNO (검색어를 쪼개서 수집 확률을 높임)
    fetch_and_process("MNO", ["통신 3사", "이통 3사"], 5, "통신 3사", p_links, p_titles)
    fetch_and_process("MNO", ["SK텔레콤", "SKT"], 5, "SKT", p_links, p_titles)
    fetch_and_process("MNO", ["KT", "케이티"], 5, "KT", p_links, p_titles)
    fetch_and_process("MNO", ["LG유플러스", "LGU+"], 5, "LG U+", p_links, p_titles)

    # 2. SUBSID
    fetch_and_process("SUBSID", ["SK텔링크", "세븐모바일"], 3, "SK텔링크", p_links, p_titles)
    fetch_and_process("SUBSID", ["KT M모바일", "KT엠모바일"], 3, "KT M모바일", p_links, p_titles)
    fetch_and_process("SUBSID", ["LG헬로비전", "헬로모바일"], 3, "LG헬로비전", p_links, p_titles)
    fetch_and_process("SUBSID", ["미디어로그", "유모바일"], 3, "미디어로그", p_links, p_titles)

    # 3. FIN / 4. SMALL (원하시는 만큼 추가 가능)
    fetch_and_process("FIN", ["KB리브모바일", "리브엠"], 3, "KB 리브모바일", p_links, p_titles)
    fetch_and_process("FIN", ["토스모바일"], 3, "토스모바일", p_links, p_titles)
