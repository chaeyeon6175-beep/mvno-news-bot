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
    """제목 간 유사도 측정 (중복 주제 방지)"""
    a = re.sub(r'[^가-힣a-zA-Z0-9]', '', a)
    b = re.sub(r'[^가-힣a-zA-Z0-9]', '', b)
    return SequenceMatcher(None, a, b).ratio()

def is_telecom_news(title):
    """불필요한 산업군(스포츠, 인사, 주가 등) 필터링"""
    t = title.lower().replace(' ', '')
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "음악회", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    """DB별/업체별 정밀 태그 분류"""
    if not is_telecom_news(title): return None
    t = title.lower().replace(' ', '')
    if any(ex in t for x in ["sk쉴더스", "지니뮤직", "kt알파"] if x in t): return None

    # MNO DB
    if db_key == "MNO":
        # 타 카테고리 기사 혼입 방지
        others = ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "토스", "우리원"]
        if any(x in t for x in others): return None
        
        sa3_kws = ["통신3사", "이통3사", "통신업계", "통신주", "이통사공통", "3사"]
        skt, kt, lg = "skt" in t or "sk텔레콤" in t, "kt" in t or "케이티" in t, "lgu+" in t or "lg유플러스" in t
        
        if any(x in t for x in sa3_kws) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]

    # 자회사/금융/중소 분류 (생략 생략되었으나 로직은 이전과 동일하게 유지)
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
    """제목 하이퍼링크 적용 노션 업로드"""
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

def collect(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    session_seen_urls = set()
    session_seen_titles = []
    final_tag_counts = {} # [중요] 실제 노션에 찍히는 태그별 개수 추적

    for keywords, limit, default_tag in configs:
        print(f"🔍 {db_key} - {default_tag} 작업 시작...")
        
        query = " ".join(keywords)
        raw_items = []
        for sort in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200: raw_items.extend(res.json().get('items', []))

        # 1. 검색 결과 내 중복 URL 즉시 제거 (1기사 1수집)
        unique_items = []
        temp_urls = set()
        for item in raw_items:
            if item['link'] not in temp_urls:
                unique_items.append(item); temp_urls.add(item['link'])

        # 2. 필터링 및 업로드
        for item in unique_items:
            if item['link'] in session_seen_urls: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            if any(get_similarity(title, st) > 0.45 for st in session_seen_titles): continue

            tags = get_final_tags(title, db_key, default_tag)
            if tags:
                tag_name = tags[0]['name']
                
                # [핵심] 태그별 12개 절대 제한 (이미 12개면 패스)
                if final_tag_counts.get(tag_name, 0) >= 12: continue

                if db_key == "MNO" and tag_name != default_tag: continue
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                
                if p_date in allowed_dates or final_tag_counts.get(tag_name, 0) < 2:
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        session_seen_urls.add(item['link'])
                        session_seen_titles.append(title)
                        final_tag_counts[tag_name] = final_tag_counts.get(tag_name, 0) + 1
        
        print(f"✅ {default_tag} 수집 종료 (누적: {final_tag_counts.get(default_tag, 0)}개)")

if __name__ == "__main__":
    # 1. MNO (30일 범위)
    collect("MNO", [(["통신3사", "통신업계", "통신주"], 12, "통신 3사"), (["SK텔레콤", "SKT"], 12, "SKT"), (["KT"], 12, "KT"), (["LG유플러스"], 12, "LG U+")], 30)
    # 2. 자회사 (60일 범위)
    collect("SUBSID", [(["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"), (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")], 60)
    # 3. 금융 (30일 범위)
    collect("FIN", [(["토스모바일"], 12, "토스모바일"), (["리브모바일", "리브M"], 12, "KB리브모바일"), (["우리원모바일"], 12, "우리원모바일")], 30)
    # 4. 중소 (60일 범위)
    collect("SMALL", [(["아이즈모바일"], 12, "아이즈모바일"), (["프리텔레콤", "프리티"], 12, "프리모바일"), (["에넥스텔레콤"], 12, "에넥스텔레콤"), (["유니컴즈"], 12, "유니컴즈"), (["인스코비"], 12, "인스코비"), (["세종텔레콤"], 12, "세종텔레콤"), (["큰사람", "이야기모바일"], 12, "큰사람")], 60)
