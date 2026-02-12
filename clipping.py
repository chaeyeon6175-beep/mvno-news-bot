import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

# 환경 변수 로드
NAVER_ID, NAVER_SECRET = os.environ.get('NAVER_CLIENT_ID'), os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_IDS = {k: os.environ.get(f'DB_ID_{k}') for k in ["MNO", "SUBSID", "FIN", "SMALL"]}
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}

def clear_notion_database(db_id):
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    if not target_id: return
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            for page in res.json().get("results", []):
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
            print(f"🗑️ DB({target_id[:5]}) 초기화 완료")
    except: pass

def is_similar(title1, title2):
    """제목 기준 8글자 이상 연속 중복 또는 높은 유사도 체크"""
    # 1. 비교를 위해 공백 및 특수문자 제거
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    
    # 2. 유사도 비율 체크 (70% 이상이면 유사로 판단)
    ratio = SequenceMatcher(None, t1, t2).ratio()
    if ratio > 0.7:
        return True
        
    # 3. 8글자 이상 연속 중복 체크 (사용자님 핵심 요청)
    match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
    if match.size >= 8:
        return True
        
    return False

def validate_link(url):
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    except: return "https://images.unsplash.com/photo-1504711434969-e33886168f5c"

def post_notion(db_id, title, link, img, tag, pub_date):
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
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
    return requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data).status_code == 200

def classify_mno(title):
    t_clean = re.sub(r'\s+', '', title).lower()
    if any(ex in t_clean for ex in ["kt알파", "ktalpha", "케이티알파"]): return None
    
    # 띄어쓰기 무시 키워드
    mno_all = ["통신3사", "이통3사", "이통사", "통신업계", "통신사"]
    skt, kt, lg = ["sk텔레콤", "skt"], ["kt", "케이티"], ["lg유플러스", "lgu+", "엘지유플러스"]
    
    if any(k in t_clean for k in mno_all) or (any(n in t_clean for n in skt) and any(n in t_clean for n in kt) and any(n in t_clean for n in lg)):
        return "통신 3사"
    
    found = []
    if any(n in t_clean for n in skt): found.append("SKT")
    if any(n in t_clean for n in kt): found.append("KT")
    if any(n in t_clean for n in lg): found.append("LG U+")
    return found[0] if len(found) == 1 else None

def collect_news(db_key, configs, processed_titles, days_range):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days_range + 1)]

    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords]) if keywords else "통신사"
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=50&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code != 200: continue
        
        count = 0
        for item in res.json().get('items', []):
            if count >= limit: break
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            if p_date not in allowed_dates: continue
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # [중복 체크] 이미 처리된 제목들과 8글자 이상 겹치는지 확인
            if any(is_similar(title, pt) for pt in processed_titles):
                continue

            matched_tag = tag
            if db_key == "MNO":
                matched_tag = classify_mno(title)
            
            if not matched_tag: continue

            img = validate_link(item['link'])
            if post_notion(db_id, title, item['link'], img, matched_tag, p_date):
                processed_titles.add(title) # 중복 검사용 리스트에 추가
                count += 1
                print(f"✅ [{matched_tag}] 수집 성공: {title[:15]}...")

if __name__ == "__main__":
    for key in DB_IDS: clear_notion_database(DB_IDS[key])
    titles = set() # 전체 수집 과정에서의 중복 제목 저장용
    
    # 1. MNO (오늘/어제)
    collect_news("MNO", [([], 15, "통신사")], titles, 1)
    
    # 2. 자회사 (오늘/어제)
    collect_news("SUBSID", [
        (["SK텔링크", "7모바일"], 3, "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 3, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 3, "LG헬로비전"),
        (["u+ 유모바일 요금제", "유플러스유모바일", "U+유모바일"], 3, "미디어로그"),
        (["미디어로그 알뜰폰"], 3, "미디어로그")
    ], titles, 1)

    # 3. 금융권 (60일 범위)
    collect_news("FIN", [
        (["리브모바일", "리브엠"], 5, "KB 리브모바일"),
        (["우리원모바일"], 3, "우리원모바일"),
        (["토스 모바일 알뜰폰"], 5, "토스모바일")
    ], titles, 60)

    # 4. 중소/기타 (60일 범위)
    collect_news("SMALL", [
        (["아이즈모바일"], 3, "아이즈모바일"),
        (["인스모바일"], 3, "인스모바일"),
        (["프리텔레콤"], 3, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 3, "에넥스텔레콤"),
        (["스노우맨"], 3, "스노우맨")
    ], titles, 60)
