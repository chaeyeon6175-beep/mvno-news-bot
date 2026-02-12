import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
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

def clear_notion_database(db_id):
    if not db_id: return
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            pages = res.json().get("results", [])
            for page in pages:
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
            print(f"🗑️ DB 초기화 완료: {target_id[:5]}")
    except: pass

def is_duplicate_by_8_chars(new_title, processed_titles):
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', new_title)
    for prev_title in processed_titles:
        t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', prev_title)
        if SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2)).size >= 8:
            return True
    return False

def post_notion(db_id, title, link, tag, pub_date, desc=""):
    """
    [주의] 아래 properties의 '제목', '날짜', '링크', '분류'는 
    노션 DB의 열(속성) 이름과 정확히 일치해야 합니다.
    """
    if not db_id: return False
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    
    img = "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    try:
        r = requests.get(link, timeout=5, headers={'User-Agent':'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
        og_img = soup.find('meta', property='og:image')
        if og_img: img = og_img['content']
    except: pass

    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]}, # 노션 DB 열 이름 확인 필수
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    
    # SK텔링크 기사에만 본문 내용 추가
    if desc and "SK텔링크" in tag:
        data["children"] = [{"object":"block","type":"paragraph","paragraph":{"rich_text":[{"type":"text","text":{"content":desc[:1000]}}]}}]
    
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def classify_mno(title):
    t = re.sub(r'\s+', '', title).lower()
    # 제외 키워드
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None
    # 자회사 키워드 (MNO 수집에서 제외하여 SUBSID로 유도)
    if any(sub in t for sub in ["sk텔링크", "7모바일", "ktm모바일", "헬로모바일"]): return None

    skt = any(x in t for x in ["skt", "sk텔레콤"])
    kt = any(x in t for x in ["kt", "케이티"])
    lg = any(x in t for x in ["lgu+", "lg유플러스"])
    
    if skt and not (kt or lg): return "SKT"
    if kt and not (skt or lg): return "KT"
    if lg and not (skt or kt): return "LG U+"
    if (sum([skt, kt, lg]) >= 2) or any(k in t for k in ["통신사", "이통사"]): return "통신 3사"
    return None

def collect(db_key, configs, processed_titles, days):
    db_id = DB_IDS.get(db_key)
    if not db_id: return

    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords])
        query += " -\"SK쉴더스\" -\"지니뮤직\""
        
        # 최신순 정렬로 고정하여 뉴스 신뢰도 확보
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code != 200: continue

        count = 0
        for item in res.json().get('items', []):
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = item['link']
            
            if is_duplicate_by_8_chars(title, processed_titles): continue

            # 분류 로직
            if db_key == "MNO":
                mno_tag = classify_mno(title)
                if mno_tag != tag: continue
                final_tag = mno_tag
            else:
                if not any(k.lower() in title.lower() for k in keywords): continue
                final_tag = tag

            # 날짜 필터 (금융/중소는 최소 2개 강제 수집)
            if (p_date in allowed_dates) or (db_key in ["FIN", "SMALL"] and count < 2):
                if post_notion(db_id, title, link, final_tag, p_date, item['description']):
                    processed_titles.add(title)
                    count += 1
                    print(f"✅ [{final_tag}] 수집 성공: {title[:20]}...")
            if count >= limit: break

if __name__ == "__main__":
    for k in DB_IDS: clear_notion_database(DB_IDS[k])
    titles = set()
    
    # 1. 자회사 (60일) - SK텔링크 최우선
    collect("SUBSID", [(["SK텔링크", "7모바일"], 10, "SK텔링크"), (["KT M모바일"], 5, "KT M모바일"), (["헬로모바일"], 5, "LG헬로비전")], titles, 60)

    # 2. MNO (7일로 확대하여 SKT 10개 확보)
    collect("MNO", [(["SK텔레콤", "SKT"], 15, "SKT"), (["KT", "케이티"], 10, "KT"), (["LG유플러스"], 10, "LG U+"), (["통신사"], 10, "통신 3사")], titles, 7)

    # 3. 금융/중소 (60일)
    collect("FIN", [(["리브모바일", "토스모바일"], 5, "금융권 알뜰폰")], titles, 60)
    collect("SMALL", [(["알뜰폰"], 5, "중소 알뜰폰")], titles, 60)
