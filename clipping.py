import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

# 1. 전역 변수 설정 (GitHub Secrets와 정확히 일치해야 함)
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
            print(f"🗑️ DB({target_id[:5]}) 초기화 완료 (삭제된 페이지: {len(pages)}개)")
    except Exception as e:
        print(f"❌ 초기화 에러: {e}")

def is_duplicate_by_8_chars(new_title, processed_titles):
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', new_title)
    for prev_title in processed_titles:
        t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', prev_title)
        match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
        if match.size >= 8: return True
    return False

def validate_link(url):
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    except: return "https://images.unsplash.com/photo-1504711434969-e33886168f5c"

def post_notion(db_id, title, link, img, tag, pub_date, content=""):
    if not db_id: return False
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
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
    
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def classify_mno_precision(title):
    t_clean = re.sub(r'\s+', '', title).lower()
    if any(ex in t_clean for ex in ["sk쉴더스", "지니뮤직", "kt알파", "ktalpha"]): return None
    if any(sub in t_clean for sub in ["sk텔링크", "7모바일", "세븐모바일", "ktm모바일", "헬로모바일", "유모바일"]): return None

    skt_k, kt_k, lg_k = ["sk텔레콤", "skt"], ["kt", "케이티"], ["lg유플러스", "lgu+", "엘지유플러스", "u플러스", "유플러스"]
    h_skt, h_kt, h_lg = any(n in t_clean for n in skt_k), any(n in t_clean for n in kt_k), any(n in t_clean for n in lg_k)
    
    if h_skt and not (h_kt or h_lg): return "SKT"
    if h_kt and not (h_skt or h_lg): return "KT"
    if h_lg and not (h_skt or h_kt): return "LG U+"
    if (sum([h_skt, h_kt, h_lg]) >= 2) or any(k in t_clean for k in ["통신3사", "이통3사", "이통사", "통신사"]): return "통신 3사"
    return None

def collect_news(db_key, configs, processed_titles, days_range):
    db_id = DB_IDS.get(db_key)
    if not db_id:
        print(f"⚠️ {db_key}용 DB_ID가 설정되지 않았습니다.")
        return
    
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days_range + 1)]
    print(f"\n--- {db_key} DB 수집 시작 (허용 날짜: {allowed_dates[0]} ~ {allowed_dates[-1]}) ---")

    for keywords, limit, tag in configs:
        query = " | ".join([f"\"{k}\"" for k in keywords]) if keywords else "알뜰폰"
        query += " -\"SK쉴더스\" -\"지니뮤직\""
        
        items = []
        for sort_opt in ["date", "sim"]:
            res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort_opt}", 
                               headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200:
                items = res.json().get('items', [])
                if items: break
            else:
                print(f"❌ 네이버 API 에러: {res.status_code}")

        count = 0
        for item in items:
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            desc = item['description'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            t_compare = title.lower().replace(' ', '')

            if is_duplicate_by_8_chars(title, processed_titles): continue

            # 분류 및 필터
            if db_key == "MNO":
                mno_check = classify_mno_precision(title)
                if mno_check != tag: continue
                final_tag, content_to_send = mno_check, ""
            else:
                if not any(k.lower().replace(' ', '') in t_compare for k in keywords): continue
                if classify_mno_precision(title) is not None: continue
                final_tag, content_to_send = tag, (desc if "SK텔링크" in tag else "")

            # 강제 수집 조건: 금융/중소는 무조건 2개 채우기, 나머지는 날짜 준수
            if (db_key in ["FIN", "SMALL"] and count < 2) or (p_date in allowed_dates):
                if post_notion(db_id, title, item['link'], validate_link(item['link']), final_tag, p_date, content_to_send):
                    processed_titles.add(title)
                    count += 1
                    print(f"✅ [{final_tag}] {p_date} 등록: {title[:20]}...")
            
            if count >= limit: break
        
        if count == 0:
            print(f"🔎 {tag} 태그로 수집된 기사가 없습니다.")

if __name__ == "__main__":
    print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. 초기화
    for k in DB_IDS:
        clear_notion_database(DB_IDS[k])
    
    titles = set()
    
    # 2. 수집 순서 및 설정
    # SUBSID: 60일 (SK텔링크 최우선)
    collect_news("SUBSID", [
        (["SK텔링크", "7모바일", "세븐모바일"], 10, "SK텔링크"),
        (["KT M모바일"], 5, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 5, "LG헬로비전")
    ], titles, 60)
    
    # MNO: 7일로 대폭 확대 (SKT 10개 이상 확실히 채우기 위함)
    collect_news("MNO", [
        (["SK텔레콤", "SKT"], 20, "SKT"),
        (["KT", "케이티"], 10, "KT"),
        (["LG유플러스"], 10, "LG U+"),
        (["통신사", "이통사"], 10, "통신 3사")
    ], titles, 7)
    
    # FIN/SMALL: 60일 (없으면 과거 기사라도 2개 강제 수집)
    collect_news("FIN", [(["리브모바일", "리브엠", "토스모바일"], 5, "금융권")], titles, 60)
    collect_news("SMALL", [(["알뜰폰"], 5, "중소 알뜰폰")], titles, 60)

    print("\n🚀 모든 수집 작업이 종료되었습니다.")
