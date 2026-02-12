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
    """DB 초기화 (수집 전 기존 기사 삭제)"""
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id or "")
    if not target_id: return
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            for page in res.json().get("results", []):
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
            print(f"🗑️ DB({target_id[:5]}) 초기화 완료")
    except: pass

def is_duplicate_by_8_chars(new_title, processed_titles):
    """8글자 이상 연속 중복 체크 (엄격한 필터)"""
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', new_title)
    for prev_title in processed_titles:
        t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', prev_title)
        match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
        if match.size >= 8: return True
    return False

def validate_link(url):
    """썸네일 추출"""
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    except: return "https://images.unsplash.com/photo-1504711434969-e33886168f5c"

def post_notion(db_id, title, link, img, tag, pub_date, content=""):
    """노션 포스팅 (뉴스 배포 날짜 사용)"""
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
    if content:
        data["children"] = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]}}]
    return requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data).status_code == 200

def classify_mno_precision(title):
    """MNO 정밀 분류 로직"""
    t_clean = re.sub(r'\s+', '', title).lower()
    if any(ex in t_clean for ex in ["kt알파", "ktalpha", "케이티알파"]): return None
    
    mno_combined = ["통신3사", "이통3사", "이통사", "통신업계", "통신사"]
    skt_k, kt_k, lg_k = ["sk텔레콤", "skt"], ["kt", "케이티"], ["lg유플러스", "lgu+", "엘지유플러스", "u플러스", "유플러스"]
    
    h_skt, h_kt, h_lg = any(n in t_clean for n in skt_k), any(n in t_clean for n in kt_k), any(n in t_clean for n in lg_k)
    
    if any(k in t_clean for k in mno_combined) or (sum([h_skt, h_kt, h_lg]) >= 2):
        return "통신 3사"
    
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
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            if p_date not in allowed_dates: continue
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            desc = item['description'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 제목 검색 필터
            if keywords and not any(k.lower().replace(' ', '') in title.lower().replace(' ', '') for k in keywords):
                continue

            # 8자 중복 필터
            if is_duplicate_by_8_chars(title, processed_titles): continue

            # MNO 분류/스킵 로직
            mno_check = classify_mno_precision(title)
            if db_key != "MNO" and mno_check is not None: continue
            if db_key == "MNO" and mno_check is None: continue

            final_tag = mno_check if db_key == "MNO" else tag
            content_to_send = desc if final_tag == "SK텔링크" else ""

            img = validate_link(item['link'])
            if post_notion(db_id, title, item['link'], img, final_tag, p_date, content_to_send):
                processed_titles.add(title)
                count += 1
                print(f"✅ [{final_tag}] ({p_date}) 수집 완료")

if __name__ == "__main__":
    for key in DB_IDS: clear_notion_database(DB_IDS[key])
    titles = set()
    
    # 1. MNO DB (1일 범위, 품질 강화 개별 쿼리)
    mno_configs = [
        (["통신 3사", "이통사", "통신사"], 5, "통신 3사"),
        (["SK텔레콤", "SKT"], 5, "SKT"),
        (["KT", "케이티"], 5, "KT"),
        (["LG유플러스", "LGU+", "엘지유플러스"], 5, "LG U+")
    ]
    collect_news("MNO", mno_configs, titles, 1)
    
    # 2. 자회사 DB (60일 범위로 확장)
    collect_news("SUBSID", [
        (["SK텔링크", "7모바일"], 3, "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 3, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 3, "LG헬로비전"),
        (["u+ 유모바일", "유플러스유모바일", "U+유모바일", "미디어로그 알뜰폰"], 3, "미디어로그")
    ], titles, 60)

    # 3. 금융권 DB (60일 범위)
    collect_news("FIN", [
        (["리브모바일", "리브엠", "국민은행 알뜰폰", "kb국민은행 알뜰폰"], 5, "KB 리브모바일"),
        (["우리원모바일", "우리은행 알뜰폰"], 3, "우리원모바일"),
        (["토스 모바일 알뜰폰"], 5, "토스모바일")
    ], titles, 60)

    # 4. 중소 DB (60일 범위)
    collect_news("SMALL", [
        (["아이즈모바일"], 3, "아이즈모바일"),
        (["인스모바일"], 3, "인스모바일"),
        (["프리텔레콤"], 3, "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 3, "에넥스텔레콤"),
        (["스노우맨"], 3, "스노우맨")
    ], titles, 60)
