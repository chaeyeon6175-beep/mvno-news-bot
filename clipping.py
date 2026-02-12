import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

# 환경 변수 로드
NAVER_ID, NAVER_SECRET = os.environ.get('NAVER_CLIENT_ID'), os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_IDS = {k: os.environ.get(f'DB_ID_{k}') for k in ["MNO", "SUBSID", "FIN", "SMALL"]}
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def is_similar(t1, t2):
    s1, s2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', t1), re.sub(r'[^가-힣a-zA-Z0-9]', '', t2)
    return SequenceMatcher(None, s1, s2).ratio() > 0.8 or SequenceMatcher(None, s1, s2).find_longest_match(0, len(s1), 0, len(s2)).size >= 8

def validate_link(url):
    try:
        h = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=h, timeout=5)
        if res.status_code != 200 or any(x in res.text for x in ["잘못된 경로", "존재하지 않는"]): return None
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1518770660439-4636190af475"
    except: return None

def post_notion(db_id, title, link, img, tag, pub_date):
    db_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    if not db_id: return False
    data = {
        "parent": {"database_id": db_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    return requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data).status_code == 200

def classify_mno(title):
    t = re.sub(r'\s+', '', title).lower()
    skt, kt, lg = any(x in t for x in ["sk텔레콤", "skt"]), any(x in t for x in ["kt", "케이티"]), any(x in t for x in ["lg유플러스", "lgu+"])
    if any(x in t for x in ["통신3사", "이통3사", "통신업"]) or (skt and kt and lg): return "통신 3사"
    if skt and not kt and not lg: return "SKT"
    if kt and not skt and not lg: return "KT"
    if lg and not skt and not kt: return "LG U+"
    return None

def fetch_and_process(db_key, configs, p_links, p_titles, days):
    db_id = DB_IDS.get(db_key)
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords])
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=50&sort=sim"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        if res.status_code != 200: continue
        
        count = 0
        for item in res.json().get('items', []):
            if count >= limit: break
            p_str = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            if p_str not in allowed_dates: continue
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link'] if 'naver.com' in item['link'] else item['originallink']
            if any(is_similar(title, pt) for pt in p_titles): continue
            if not any(k.lower() in title.lower() for k in keywords): continue
            
            final_tag = classify_mno(title) if db_key == "MNO" else tag
            if not final_tag: continue
            
            img = validate_link(link)
            if img and post_notion(db_id, title, link, img, final_tag, p_str):
                p_links.add(link); p_titles.add(title); count += 1
                print(f"✅ {final_tag} 수집: {title[:15]}...")

if __name__ == "__main__":
    l, t = set(), set()
    fetch_and_process("MNO", [(["통신 3사", "이통 3사"], 5, "통신 3사"), (["SK텔레콤", "SKT"], 5, "SKT"), (["KT", "케이티"], 5, "KT"), (["LG유플러스", "LGU+"], 5, "LG U+")], l, t, 5)
    fetch_and_process("SUBSID", [(["SK텔링크", "세븐모바일"], 3, "SK텔링크"), (["KT M모바일"], 3, "KT M모바일"), (["LG헬로비전"], 3, "LG헬로비전"), (["미디어로그", "유모바일"], 3, "미디어로그")], l, t, 5)
    fetch_and_process("FIN", [(["KB리브모바일", "리브엠"], 5, "KB 리브모바일"), (["토스모바일"], 5, "토스모바일"), (["우리원모바일"], 5, "우리원모바일")], l, t, 60)
    fetch_and_process("SMALL", [(["아이즈모바일"], 3, "아이즈모바일"), (["프리텔레콤"], 3, "프리텔레콤"), (["에넥스텔레콤"], 3, "에넥스텔레콤"), (["인스모바일"], 3, "인스모바일")], l, t, 60)
