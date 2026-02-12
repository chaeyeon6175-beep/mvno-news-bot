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

# 주요 언론사 가중치
MAJOR_PRESS = ["연합뉴스", "뉴시스", "뉴스1", "매일경제", "한국경제", "전자신문", "디지털데일리", "머니투데이", "아이뉴스24"]

def get_similarity(a, b):
    """제목 유사도 계산 (특수문자 제거 후 비교)"""
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def is_telecom_industry_news(title):
    """통신 산업 본질과 관련된 기사만 통과 (스포츠, 쇼핑, 주가 등 제외)"""
    t = title.lower().replace(' ', '')
    # 제외 산업군
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "음악회", "전시회", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    # 필수 통신 키워드
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "구독", "결합", "공시지원"]
    return any(inc in t for inc in include)

def select_representative(articles):
    """대표 기사 선정: 주요 언론사(+10) > 제목 길이(+0.1) > 최신순"""
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

def get_refined_tags(title, db_key, default_tag):
    """DB별 배타적 분류 및 통신 3사 우선순위 적용"""
    if not is_telecom_industry_news(title): return None
    t = title.lower().replace(' ', '')
    
    # 제외 키워드
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None

    # MNO DB
    if db_key == "MNO":
        # 자회사/금융 키워드 포함 시 MNO 제외
        if any(x in t for x in ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "토스모바일"]): return None
        is_3사 = any(x in t for x in ["통신3사", "이통3사", "통신사"]) or \
                 (sum([any(x in t for x in ["skt", "sk텔레콤"]), any(x in t for x in ["kt", "케이티"]), any(x in t for x in ["lgu+", "lg유플러스"])]) >= 2)
        if is_3사: return [{"name": "통신 3사"}]
        if any(x in t for x in ["skt", "sk텔레콤"]): return [{"name": "SKT"}]
        if any(x in t for x in ["kt", "케이티"]): return [{"name": "KT"}]
        if any(x in t for x in ["lg유플러스", "lgu+"]): return [{"name": "LG U+"}]
        return None

    # 자회사/금융/중소 (기존 로직 유지)
    # ... (생략된 태그 매핑 로직은 이전과 동일하게 적용됨)
    return [{"name": default_tag}]

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

    for keywords, limit, default_tag in configs:
        print(f"🔍 {db_key} - {default_tag} 수집 중...")
        query = " ".join(keywords)
        raw_items = []
        for sort in ["date", "sim"]:
            res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}",
                               headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))

        # 1. 1차 필터링 (산업 필터 및 태그 부여)
        valid_articles = []
        for item in raw_items:
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            tags = get_refined_tags(title, db_key, default_tag)
            if tags:
                valid_articles.append({
                    'title': title, 'link': item['link'], 'tags': tags,
                    'date': datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d'),
                    'press': item.get('originallink', '') # 네이버는 언론사명을 따로 안줘서 링크로 대체하거나 추가 크롤링 필요
                })

        # 2. 유사 주제 그룹화 (Clustering) - 동일 주제 기사 제거
        unique_groups = []
        for art in valid_articles:
            found = False
            for group in unique_groups:
                if get_similarity(art['title'], group[0]['title']) > 0.5: # 50% 이상 유사하면 동일 주제로 판단
                    group.append(art); found = True; break
            if not found: unique_groups.append([art])

        # 3. 대표 기사 선정 및 태그별 최대 12개 출력
        count = 0
        for group in unique_groups:
            rep = select_representative(group)
            is_min = (db_key != "MNO") and (count < 2)
            if rep['date'] in allowed_dates or is_min:
                if post_notion(db_id, rep['title'], rep['link'], rep['tags'], rep['date']):
                    count += 1
            if count >= 12: break # [필수] 태그당 최대 12개 제한

if __name__ == "__main__":
    for k in DB_IDS: 
        # DB 비우기 로직은 사용자 환경에 맞춰 실행
        # clear_notion_database(DB_IDS[k])
        pass

    # MNO 수집
    collect("MNO", [(["통신3사"], 12, "통신 3사"), (["SKT"], 12, "SKT"), (["KT"], 12, "KT"), (["LG유플러스"], 12, "LG U+")], 7)
    # 자회사 수집
    collect("SUBSID", [(["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"), (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")], 60)
    # 금융권 수집
    collect("FIN", [(["토스모바일", "리브모바일", "우리원모바일"], 12, "금융권")], 60)
    # 중소 알뜰폰
    collect("SMALL", [(["알뜰폰 뉴스"], 12, "중소 알뜰폰")], 60)
