import os, requests, re, time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 1. 환경 변수 설정
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

def get_similarity(a, b):
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def check_already_collected(db_id):
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    filter_data = {"filter": {"property": "날짜", "rich_text": {"equals": today}}, "page_size": 1}
    res = requests.post(url, headers=HEADERS, json=filter_data)
    return len(res.json().get('results', [])) > 0 if res.status_code == 200 else False

def is_telecom_news(title):
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "주가", "증시", "상장"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "출시"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    if not is_telecom_news(title): return None
    t = title.lower().replace(' ', '')
    if db_key == "MNO":
        sa3_kws = ["통신3사", "이통3사", "통신업계", "3사"]
        skt, kt, lg = "skt" in t or "sk텔레콤" in t, "kt" in t or "케이티" in t, "lgu+" in t or "lg유플러스" in t
        if any(x in t for x in sa3_kws) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]
    maps = {
        "SUBSID": {"SK텔링크": ["sk텔링크", "7모바일"], "KT M모바일": ["ktm모바일", "kt엠모바일"], "LG헬로비전": ["lg헬로비전", "헬로모바일"], "KT스카이라이프": ["스카이라이프"], "미디어로그": ["미디어로그", "유모바일"]},
        "FIN": {"토스모바일": ["토스모바일", "토스"], "우리원모바일": ["우리원모바일", "우리원"], "KB리브모바일": ["리브모바일", "리브m", "kb국민"]},
        "SMALL": {"아이즈모바일": ["아이즈모바일"], "프리모바일": ["프리텔레콤", "프리티"], "에넥스텔레콤": ["에넥스텔레콤", "a모바일"], "유니컴즈": ["유니컴즈", "모비스트"], "인스코비": ["인스코비"], "세종텔레콤": ["세종텔레콤", "스노우맨"], "큰사람": ["큰사람", "이야기모바일"]}
    }
    if db_key in maps:
        for name, kws in maps[db_key].items():
            if any(k in t for k in kws): return [{"name": name}]
    return None

def post_notion(db_id, title, link, tags, pub_date):
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    data = {
        "parent": {"database_id": target_id},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "날짜": {"rich_text": [{"text": {"content": pub_date}}]},
            "링크": {"url": link},
            "분류": {"multi_select": tags}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    return res.status_code == 200

# --- 1번 DB 수집 (개별 사 선점 + 총 30개 제한) ---
def collect_mno(days=7):
    db_id = DB_IDS.get("MNO")
    if check_already_collected(db_id):
        print("⚠️ 오늘 이미 1번 DB 수집 완료")
        return

    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    mno_seen_urls, mno_seen_titles = set(), []
    total_count = 0  # DB 전체 카운트

    configs = [
        (["SK텔레콤", "SKT"], "SKT"), (["KT", "케이티"], "KT"),
        (["LG유플러스", "LGU+"], "LG U+"), (["통신3사", "통신업계"], "통신 3사")
    ]

    for keywords, target_tag in configs:
        if total_count >= 30: break # 전체 30개 넘으면 종료
        tag_count = 0
        query = " ".join(keywords)
        for sort in ["sim", "date"]:
            if total_count >= 30 or tag_count >= 12: break
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code != 200: continue
            
            for item in res.json().get('items', []):
                if total_count >= 30 or tag_count >= 12: break
                if item['link'] in mno_seen_urls: continue
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                if any(get_similarity(title, st) > 0.45 for st in mno_seen_titles): continue
                
                tags = get_final_tags(title, "MNO", target_tag)
                if tags and tags[0]['name'] == target_tag:
                    p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                    if p_date in allowed_dates:
                        if post_notion(db_id, title, item['link'], tags, p_date):
                            mno_seen_urls.add(item['link'])
                            mno_seen_titles.append(title)
                            tag_count += 1
                            total_count += 1
    print(f"✅ MNO 수집 종료 (총 {total_count}개)")

# --- 2,3,4번 DB 수집 (총 30개 제한 유지) ---
def collect_others(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    total_count = 0
    
    for keywords, limit, default_tag in configs:
        if total_count >= 30: break
        tag_count = 0
        query = " ".join(keywords)
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        if res.status_code != 200: continue
        
        for item in res.json().get('items', []):
            if total_count >= 30 or tag_count >= 12: break
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_final_tags(title, db_key, default_tag)
            if tags:
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                if p_date in allowed_dates or tag_count < 2:
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        tag_count += 1
                        total_count += 1
    print(f"✅ {db_key} 수집 종료 (총 {total_count}개)")

if __name__ == "__main__":
    collect_mno(days=7)
    collect_others("SUBSID", [(["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"), (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")], 60)
    collect_others("FIN", [(["토스모바일"], 12, "토스모바일"), (["리브모바일"], 12, "KB리브모바일"), (["우리원모바일"], 12, "우리원모바일")], 30)
    collect_others("SMALL", [(["아이즈모바일"], 12, "아이즈모바일"), (["프리텔레콤"], 12, "프리모바일"), (["에넥스텔레콤"], 12, "에넥스텔레콤"), (["유니컴즈"], 12, "유니컴즈"), (["인스코비"], 12, "인스코비"), (["세종텔레콤"], 12, "세종텔레콤"), (["큰사람"], 12, "큰사람")], 60)
