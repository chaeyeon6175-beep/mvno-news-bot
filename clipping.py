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
    """수집 전 기존 뉴스 삭제(아카이브)"""
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    if not target_id: return
    query_url = f"https://api.notion.com/v1/databases/{target_id}/query"
    try:
        res = requests.post(query_url, headers=HEADERS)
        if res.status_code == 200:
            for page in res.json().get("results", []):
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
            print(f"🗑️ DB({target_id[:5]}) 초기화 완료")
    except: pass

def is_similar(title1, title2):
    """8글자 이상 연속 중복 또는 유사도 70% 이상 체크"""
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    ratio = SequenceMatcher(None, t1, t2).ratio()
    match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
    return ratio > 0.7 or match.size >= 8

def validate_link(url):
    """링크 유효성 및 썸네일(og:image) 추출"""
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    except: return "https://images.unsplash.com/photo-1504711434969-e33886168f5c"

def post_notion(db_id, title, link, img, tag, pub_date):
    """노션에 페이지 생성 (pub_date: 뉴스 배포 날짜)"""
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]}, # 뉴스 배포날짜 출력
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    return requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data).status_code == 200

def classify_mno(title):
    """통신 3사 본체 및 의장 관련 기사 판별 (MNO 전용)"""
    t_clean = re.sub(r'\s+', '', title).lower()
    if any(ex in t_clean for ex in ["kt알파", "ktalpha", "케이티알파"]): return None
    
    mno_all = ["통신3사", "이통3사", "이통사", "통신업계", "통신사"]
    skt, kt, lg = ["sk텔레콤", "skt"], ["kt", "케이티"], ["lg유플러스", "lgu+", "엘지유플러스", "u플러스", "유플러스"]
    
    if any(k in t_clean for k in mno_all): return "통신 3사"
    
    h_skt, h_kt, h_lg = any(n in t_clean for n in skt), any(n in t_clean for n in kt), any(n in t_clean for n in lg)
    if (h_skt and h_kt) or (h_kt and h_lg) or (h_skt and h_lg): return "통신 3사"
    if h_skt: return "SKT"
    if h_kt: return "KT"
    if h_lg: return "LG U+"
    return None

def collect_news(db_key, configs, processed_titles, days_range):
    """뉴스 수집 핵심 로직"""
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days_range + 1)]

    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords]) if keywords else "통신사"
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code != 200: continue
        
        count = 0
        for item in res.json().get('items', []):
            if count >= limit: break
            
            # [날짜] 수집일이 아닌 실제 뉴스 배포 날짜 추출
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            if p_date not in allowed_dates: continue
            
            # [제목] HTML 태그 제거 및 제목 기반 필터링
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            if keywords and not any(k.lower().replace(' ', '') in title.lower().replace(' ', '') for k in keywords):
                continue

            # [중복] 8글자 이상 일치 시 제외
            if any(is_similar(title, pt) for pt in processed_titles): continue

            # [MNO 우선] 본체 기사라면 다른 DB 수집 중이라도 패스 (1번 DB 선점용)
            mno_check = classify_mno(title)
            if db_key != "MNO" and mno_check is not None: continue

            matched_tag = mno_check if db_key == "MNO" else tag
            if not matched_tag: continue

            img = validate_link(item['link'])
            if post_notion(db_id, title, item['link'], img, matched_tag, p_date):
                processed_titles.add(title)
                count += 1
                print(f"✅ [{matched_tag}] ({p_date}) 수집 성공")

if __name__ == "__main__":
    for key in DB_IDS: clear_notion_database(DB_IDS[key])
    titles = set()
    
    # 1. MNO DB (통신 3사 본체)
    collect_news("MNO", [([], 20, "통신사")], titles, 1)
    
    # 2. 자회사 DB
    collect_news("SUBSID", [
        (["SK텔링크", "7모바일"], 3, "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 3, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 3, "LG헬로비전"),
        (["u+ 유모바일", "유플러스유모바일", "U+유모바일", "미디어로그 알뜰폰"], 3, "미디어로그")
    ], titles, 1)

    # 3. 금융권 DB (KB/우리은행 키워드 확장)
    collect_news("FIN", [
        (["리브모바일", "리브엠", "국민은행 알뜰폰", "kb국민은행 알뜰폰"], 5, "KB 리브모바일"),
        (["우리원모바일", "우리은행 알뜰폰"], 3, "우리원모바일"),
        (["토스 모바일 알뜰폰"], 5, "토스모바일")
    ], titles, 60)

    # 4. 중소/기타 DB
    collect_news("SMALL", [
        (["아이즈모바일"], 3, "아이즈모바일"),
        (["인스모바일"], 3, "인스모바일"),
        (["프리텔레콤"], 3, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 3, "에넥스텔레콤"),
        (["스노우맨"], 3, "스노우맨")
    ], titles, 60)
