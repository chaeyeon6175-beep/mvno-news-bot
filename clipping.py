import os, requests, re, time
from datetime import datetime, timedelta
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

# 주요 언론사 가중치 (대표 기사 선정용)
MAJOR_PRESS = ["연합뉴스", "뉴시스", "뉴스1", "매일경제", "한국경제", "전자신문", "디지털데일리", "머니투데이"]

def get_similarity(a, b):
    """제목 간의 유사도 측정"""
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def is_telecom_industry_news(title):
    """스포츠, 쇼핑, 단순 인사 소식 등 노이즈 필터링"""
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "음악회", "전시회", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "공시지원"]
    return any(inc in t for inc in include)

def select_representative(articles):
    """그룹 내 최적의 기사 1개 선정 (언론사 신뢰도 > 제목 길이)"""
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

def get_final_tags(title, db_key, default_tag):
    """제목에 명시된 이름에 따라 태그를 부여하는 핵심 로직"""
    if not is_telecom_industry_news(title): return None
    t = title.lower().replace(' ', '')
    
    # 0. 제외 키워드
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None

    # 1. MNO DB (이통3사 본업)
    if db_key == "MNO":
        # 자회사나 금융권 키워드 포함 시 MNO에서 제외
        if any(x in t for x in ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "토스모바일"]): return None
        
        skt = any(x in t for x in ["skt", "sk텔레콤"])
        kt = any(x in t for x in ["kt", "케이티"])
        lg = any(x in t for x in ["lgu+", "lg유플러스"])
        
        if (skt + kt + lg >= 2) or any(x in t for x in ["3사", "이통사공통"]):
            return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]

    # 2. 자회사 DB (입력한 5개사 명확 분류)
    elif db_key == "SUBSID":
        subsid_map = {
            "SK텔링크": ["sk텔링크", "7모바일", "세븐모바일"],
            "KT M모바일": ["ktm모바일", "kt엠모바일"],
            "LG헬로비전": ["lg헬로비전", "헬로모바일"],
            "KT스카이라이프": ["스카이라이프", "skylife"],
            "미디어로그": ["미디어로그", "유모바일", "u모바일"]
        }
        for name, kws in subsid_map.items():
            if any(k in t for k in kws): return [{"name": name}]
        return None

    # 3. 금융 DB (금융권 3사)
    elif db_key == "FIN":
        fin_map = {"토스모바일": ["토스모바일"], "우리원모바일": ["우리원모바일"], "KB리브모바일": ["리브모바일", "리브m"]}
        for name, kws in fin_map.items():
            if any(k in t for k in kws): return [{"name": name}]
        return None

    # 4. 중소회사 DB (기타 알뜰폰)
    elif db_key == "SMALL":
        major_kws = ["skt", "sk텔레콤", "kt", "케이티", "lg유플러스", "텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브", "토스", "우리원"]
        if any(x in t for x in major_kws): return None
        return [{"name": "중소 알뜰폰"}]
    
    return None

def post_notion(db_id, title, link, tags, pub_date):
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
    processed_urls = set()

    for keywords, limit, default_tag in configs:
        tag_count = 0 # 태그별 12개 제한용 카운트
        print(f"🔍 {db_key} - {default_tag} 수집 시작...")
        
        query = " ".join(keywords)
        raw_items = []
        for sort in ["date", "sim"]:
            res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}",
                               headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))

        # 1. 1차 필터링 및 태그 확정
        valid_articles = []
        for item in raw_items:
            if item['link'] in processed_urls: continue
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_final_tags(title, db_key, default_tag)
            
            # MNO의 경우, 현재 검색 태그와 기사 분석 태그가 일치할 때만 수집 (정확도 확보)
            if tags:
                if db_key == "MNO" and tags[0]['name'] != default_tag: continue
                
                valid_articles.append({
                    'title': title, 'link': item['link'], 'tags': tags,
                    'date': datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d'),
                    'press': item.get('originallink', '')
                })

        # 2. 유사 주제 그룹화 (유사도 0.5 기준)
        unique_groups = []
        for art in valid_articles:
            found = False
            for group in unique_groups:
                if get_similarity(art['title'], group[0]['title']) > 0.5:
                    group.append(art); found = True; break
            if not found: unique_groups.append([art])

        # 3. 대표 기사 선정 및 노션 등록 (태그당 최대 12개)
        for group in unique_groups:
            if tag_count >= 12: break
            rep = select_representative(group)
            is_min = (db_key != "MNO") and (tag_count < 2)
            
            if rep['date'] in allowed_dates or is_min:
                if post_notion(db_id, rep['title'], rep['link'], rep['tags'], rep['date']):
                    processed_urls.add(rep['link'])
                    tag_count += 1

if __name__ == "__main__":
    # 1. 자회사 (각 자회사별로 검색하여 태그당 12개씩)
    collect("SUBSID", [
        (["SK텔링크", "7모바일"], 12, "SK텔링크"),
        (["KT엠모바일"], 12, "KT M모바일"),
        (["LG헬로비전", "헬로모바일"], 12, "LG헬로비전"),
        (["스카이라이프"], 12, "KT스카이라이프"),
        (["미디어로그", "유모바일"], 12, "미디어로그")
    ], 60)

    # 2. MNO (3사 공통/단독 각각 12개씩)
    collect("MNO", [
        (["통신3사", "이통사"], 12, "통신 3사"),
        (["SK텔레콤", "SKT"], 12, "SKT"),
        (["KT"], 12, "KT"),
        (["LG유플러스"], 12, "LG U+")
    ], 7)

    # 3. 금융권 (3사 통합 12개)
    collect("FIN", [(["토스모바일", "리브모바일", "우리원모바일"], 12, "금융권")], 60)

    # 4. 중소 알뜰폰 (통합 12개)
    collect("SMALL", [(["알뜰폰"], 12, "중소 알뜰폰")], 60)
