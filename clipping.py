import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

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

def clear_notion_database(db_id):
    if not db_id: return
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            for page in res.json().get("results", []):
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
    except: pass

def get_priority_tags(title, default_tag):
    t = title.lower().replace(' ', '')
    
    # [검수 1] 제외 키워드 로직 (절대 누락 금지)
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파", "ktalpha"]):
        return None

    tags = set()
    # [검수 2] 통신 3사 우선 분류 로직
    is_3사 = any(x in t for x in ["통신3사", "이통3사", "통신사", "이통사"]) or \
             (sum([any(x in t for x in ["sk텔레콤", "skt"]), 
                   any(x in t for x in ["kt", "케이티"]), 
                   any(x in t for x in ["lg유플러스", "lgu+"])]) >= 2)

    if is_3사:
        tags.add("통신 3사")
    else:
        if any(x in t for x in ["sk텔레콤", "skt"]): tags.add("SKT")
        elif any(x in t for x in ["kt", "케이티"]): tags.add("KT")
        elif any(x in t for x in ["lg유플러스", "lgu+", "엘지유플러스"]): tags.add("LG U+")
    
    if not tags: tags.add(default_tag)
    elif default_tag in ["SK텔링크", "KT M모바일", "LG헬로비전", "금융권", "중소 알뜰폰"]:
        tags.add(default_tag)

    return [{"name": tag} for tag in tags]

def post_notion(db_id, title, link, tags, pub_date):
    if not db_id: return False
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    data = {
        "parent": {"database_id": target_id},
        "properties": {
            "제목": {"title": [{"text": {"content": title}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": tags}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

def collect(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    print(f"🔍 {db_key} 데이터베이스 작업 시작...")

    for keywords, limit, default_tag in configs:
        real_limit = min(limit, 12) # [검수 3] 12개 제한
        query = " ".join(keywords)
        
        items = []
        for sort_type in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort_type}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200:
                items.extend(res.json().get('items', []))
            if items: break

        count = 0
        for item in items:
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # [검수 4] 자회사/금융/중소 최소 2개 보장 로직
            is_min_guaranteed = (db_key in ["SUBSID", "FIN", "SMALL"]) and (count < 2)
            
            if p_date in allowed_dates or is_min_guaranteed:
                priority_tags = get_priority_tags(title, default_tag)
                if priority_tags is None: continue
                
                # MNO 세부 필터링
                if db_key == "MNO":
                    tag_names = [t['name'] for t in priority_tags]
                    if default_tag not in tag_names: continue

                if post_notion(db_id, title, item['link'], priority_tags, p_date):
                    count += 1
            if count >= real_limit: break

if __name__ == "__main__":
    for k in DB_IDS: clear_notion_database(DB_IDS[k])
    
    collect("SUBSID", [
        (["SK텔링크", "7모바일"], 12, "SK텔링크"),
        (["KT M모바일"], 12, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 12, "LG헬로비전")
    ], 60)

    collect("MNO", [
        (["통신3사", "이통3사", "통신사"], 12, "통신 3사"),
        (["SK텔레콤", "SKT"], 12, "SKT"),
        (["KT", "케이티"], 12, "KT"),
        (["LG유플러스"], 12, "LG U+")
    ], 7)

    collect("FIN", [(["리브모바일", "토스모바일"], 12, "금융권")], 60)
    collect("SMALL", [(["알뜰폰"], 12, "중소 알뜰폰")], 60)

    print("🏁 모든 필터링 및 우선순위가 반영된 수집 완료!")
