import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
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

# 주요 언론사 가중치 (대표 기사 선정 시 사용)
MAJOR_PRESS = ["연합뉴스", "뉴시스", "뉴스1", "매일경제", "한국경제", "전자신문", "디지털데일리", "머니투데이"]

def clear_notion_database(db_id):
    if not db_id: return
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            for page in res.json().get("results", []):
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
    except: pass

def get_similarity(a, b):
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def select_representative(articles):
    """최신성, 제목 구체성, 언론사 신뢰도를 기준으로 대표 기사 1개 선정"""
    best_score = -1
    best_art = articles[0]
    for art in articles:
        score = 0
        if any(p in art['press'] for p in MAJOR_PRESS): score += 10
        score += len(art['title']) * 0.1
        if score >= best_score:
            best_score = score
            best_art = art
    return best_art

def get_db_specific_tags(title, db_key, default_tag):
    """DB간 영역 침범 방지 및 태그 부여 로직"""
    t = title.lower().replace(' ', '')
    
    # [공통] 제외 키워드 필터
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파", "ktalpha"]): return None

    # [영역 침범 방지 키워드셋]
    mno_kws = ["sk텔레콤", "skt", "kt", "케이티", "lg유플러스", "lgu+", "엘지유플러스"]
    subsid_kws = ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그"]
    fin_kws = ["리브모바일", "리브m", "토스모바일", "우리원모바일"]

    # 1. MNO DB 필터링
    if db_key == "MNO":
        if any(x in t for x in (subsid_kws + fin_kws)): return None
        if not any(x in t for x in mno_kws + ["통신사", "이통사"]): return None
        
        # MNO 내 세부 분류 (통신 3사 우선)
        is_3사 = any(x in t for x in ["통신3사", "이통3사", "통신사"]) or \
                 (sum([any(x in t for x in ["skt", "sk텔레콤"]), any(x in t for x in ["kt", "케이티"]), any(x in t for x in ["lgu+", "lg유플러스"])]) >= 2)
        if is_3사: return [{"name": "통신 3사"}]
        if any(x in t for x in ["skt", "sk텔레콤"]): return [{"name": "SKT"}]
        if any(x in t for x in ["kt", "케이티"]): return [{"name": "KT"}]
        if any(x in t for x in ["lgu+", "lg유플러스"]): return [{"name": "LG U+"}]

    # 2. 자회사 DB 필터링
    elif db_key == "SUBSID":
        subsid_map = {
            "SK텔링크": ["sk텔링크", "7모바일"],
            "KT M모바일": ["ktm모바일", "kt엠모바일"],
            "LG헬로비전": ["lg헬로비전", "헬로모바일"],
            "KT스카이라이프": ["스카이라이프"],
            "미디어로그": ["미디어로그", "유모바일"]
        }
        for name, kws in subsid_map.items():
            if any(x in t for x in kws): return [{"name": name}]
        return None

    # 3. 금융 DB 필터링
    elif db_key == "FIN":
        fin_map = {
            "KB리브모바일": ["리브모바일", "리브m"],
            "토스모바일": ["토스모바일"],
            "우리원모바일": ["우리원모바일"]
        }
        for name, kws in fin_map.items():
            if any(x in t for x in kws): return [{"name": name}]
        return None

    # 4. 중소회사 DB 필터링 (메이저 키워드 포함 시 제외)
    elif db_key == "SMALL":
        if not "알뜰폰" in t: return None
        if any(x in t for x in (mno_kws + subsid_kws + fin_kws)): return None
        return [{"name": "중소 알뜰폰"}]

    return None

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
    print(f"🔍 {db_key} 데이터베이스 최적화 수집 중...")

    for keywords, limit, default_tag in configs:
        query = " ".join(keywords)
        raw_items = []
        for sort_type in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort_type}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))
        
        # 1. 유효성 검사 및 정형화
        valid_articles = []
        for item in raw_items:
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_db_specific_tags(title, db_key, default_tag)
            if tags:
                valid_articles.append({
                    'title': title, 'link': item['link'], 'tags': tags,
                    'date': datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d'),
                    'press': item.get('originallink', '')
                })

        # 2. 유사 기사 그룹화 (Clustering)
        unique_groups = []
        for art in valid_articles:
            found = False
            for group in unique_groups:
                if get_similarity(art['title'], group[0]['title']) > 0.6:
                    group.append(art); found = True; break
            if not found: unique_groups.append([art])

        # 3. 대표 기사 선정 및 등록
        count = 0
        for group in unique_groups:
            rep = select_representative(group)
            is_min = (db_key != "MNO") and (count < 2) # 최소 2개 보장
            if rep['date'] in allowed_dates or is_min:
                if post_notion(db_id, rep['title'], rep['link'], rep['tags'], rep['date']):
                    count += 1
            if count >= min(limit, 12): break

if __name__ == "__main__":
    for k in DB_IDS: clear_notion_database(DB_IDS[k])
    
    # 1. 자회사 (5개사)
    collect("SUBSID", [(["SK텔링크", "KT엠모바일", "LG헬로비전", "스카이라이프", "미디어로그"], 12, "자회사")], 60)
    # 2. MNO (순수 3사)
    collect("MNO", [(["통신3사"], 12, "통신 3사"), (["SKT"], 12, "SKT"), (["KT"], 12, "KT"), (["LG유플러스"], 12, "LG U+")], 7)
    # 3. 금융
    collect("FIN", [(["토스모바일", "리브모바일", "우리원모바일"], 12, "금융권")], 60)
    # 4. 중소
    collect("SMALL", [(["알뜰폰"], 12, "중소 알뜰폰")], 60)

    print("🏁 모든 필터링, 그룹화, 대표 기사 선정 프로세스가 완료되었습니다.")
