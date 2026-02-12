import os, requests, re, time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 1. 환경 변수 및 기본 설정
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

# 1번 DB 중복 실행 방지용 체크 함수
def check_already_collected(db_id):
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    filter_data = {
        "filter": {"property": "날짜", "rich_text": {"equals": today}},
        "page_size": 1
    }
    res = requests.post(url, headers=HEADERS, json=filter_data)
    if res.status_code == 200:
        return len(res.json().get('results', [])) > 0
    return False

def is_telecom_news(title):
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    if not is_telecom_news(title): return None
    t = title.lower().replace(' ', '')
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None

    if db_key == "MNO":
        others = ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "토스", "우리원"]
        if any(x in t for x in others): return None
        sa3_kws = ["통신3사", "이통3사", "통신업계", "통신주", "이통사공통", "3사"]
        skt, kt, lg = "skt" in t or "sk텔레콤" in t, "kt" in t or "케이티" in t, "lgu+" in t or "lg유플러스" in t
        if any(x in t for x in sa3_kws) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]
    
    # 2,3,4번은 업체명이 제목에 있는 경우에만 태그 출력 (사용자 요청 원복)
    maps = {
        "SUBSID": {"SK텔링크": ["sk텔링크", "7모바일"], "KT M모바일": ["ktm모바일", "kt엠모바일"], "LG헬로비전": ["lg헬로비전", "헬로모바일"], "KT스카이라이프": ["스카이라이프"], "미디어로그": ["미디어로그", "유모바일"]},
        "FIN": {"토스모바일": ["토스모바일", "토스"], "우리원모바일": ["우리원모바일", "우리원"], "KB리브모바일": ["리브모바일", "리브m"]},
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

# --- 1번 DB 전용 수집 (1주일 제한 + 중복 방지 강화) ---
def collect_mno(days=7):
    db_id = DB_IDS.get("MNO")
    if check_already_collected(db_id):
        print("⚠️ 오늘 이미 1번 DB 수집이 완료되었습니다.")
        return

    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    mno_seen_urls = set()
    mno_seen_titles = []
    mno_tag_counts = {"통신 3사": 0, "SKT": 0, "KT": 0, "LG U+": 0}

    configs = [
        (["통신3사", "통신업계"], "통신 3사"),
        (["SK텔레콤", "SKT"], "SKT"),
        (["KT", "케이티"], "KT"),
        (["LG유플러스", "LGU+"], "LG U+")
    ]

    for keywords, target_tag in configs:
        query = " ".join(keywords)
        raw_items = []
        for sort in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))

        unique_items = []
        _tmp = set()
        for i in raw_items:
            if i['link'] not in _tmp: unique_items.append(i); _tmp.add(i['link'])

        for item in unique_items:
            if mno_tag_counts[target_tag] >= 12: break
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
                        mno_tag_counts[target_tag] += 1

# --- 2,3,4번 DB 전용 수집 (기존 방식 절대 유지) ---
def collect_others(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    for keywords, limit, default_tag in configs:
        tag_count = 0
        seen_urls = set()
        query = " ".join(keywords)
        # 2,3,4번은 기존처럼 '알뜰폰' 등을 포함한 키워드로 수집
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        if res.status_code != 200: continue
        
        for item in res.json().get('items', []):
            if tag_count >= 12: break
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_final_tags(title, db_key, default_tag)
            # 업체명이 제목에 포함된 경우에만 출력하는 로직 유지
            if tags:
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                if p_date in allowed_dates or tag_count < 2:
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        tag_count += 1

if __name__ == "__main__":
    # 1. 1번 데이터베이스: 1주일 제한 + 깃허브 중복 방지 적용
    collect_mno(days=7)

    # 2, 3, 4. 데이터베이스: 기존 로직 그대로 유지
    collect_others("SUBSID", [
        (["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"),
        (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")
    ], 60)
    collect_others("FIN", [(["토스모바일"], 12, "토스모바일"), (["리브모바일"], 12, "KB리브모바일"), (["우리원모바일"], 12, "우리원모바일")], 30)
    collect_others("SMALL", [(["아이즈모바일"], 12, "아이즈모바일"), (["프리텔레콤"], 12, "프리모바일"), (["에넥스텔레콤"], 12, "에넥스텔레콤"), (["유니컴즈"], 12, "유니컴즈"), (["인스코비"], 12, "인스코비"), (["세종텔레콤"], 12, "세종텔레콤"), (["큰사람"], 12, "큰사람")], 60)
