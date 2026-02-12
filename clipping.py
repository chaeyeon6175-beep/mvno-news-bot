import os, requests, re, time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 환경 변수 로드 (사전에 설정 필요)
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

def is_telecom_industry_news(title):
    t = title.lower().replace(' ', '')
    # 스포츠, 쇼핑, 주가 등 통신 서비스와 무관한 산업군 배제
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "음악회", "전시회", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    # 통신 산업 핵심 키워드 포함 여부
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "공시지원"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    if not is_telecom_industry_news(title): return None
    t = title.lower().replace(' ', '')
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None

    # 1. MNO DB (통신3사)
    if db_key == "MNO":
        if any(x in t for x in ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "토스모바일"]): return None
        sa3_keywords = ["통신3사", "이통3사", "통신업계", "통신주", "이통사공통", "3사"]
        skt, kt, lg = any(x in t for x in ["skt", "sk텔레콤"]), any(x in t for x in ["kt", "케이티"]), any(x in t for x in ["lgu+", "lg유플러스"])
        if any(x in t for x in sa3_keywords) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]

    # 2. 자회사 DB (5개사)
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

    # 3. 금융 DB (3사)
    elif db_key == "FIN":
        fin_map = {"토스모바일": ["토스모바일"], "우리원모바일": ["우리원모바일"], "KB리브모바일": ["리브모바일", "리브m"]}
        for name, kws in fin_map.items():
            if any(k in t for k in kws): return [{"name": name}]
        return None

    # 4. 중소 사업자 DB (지정 업체명이 제목에 있을 때만 출력)
    elif db_key == "SMALL":
        small_map = {
            "아이즈모바일": ["아이즈모바일", "아이즈비전"],
            "프리모바일": ["프리텔레콤", "프리모바일"],
            "에넥스텔레콤": ["에넥스텔레콤", "a모바일"],
            "유니컴즈": ["유니컴즈", "모비스트"],
            "인스코비": ["인스코비", "프리티"],
            "세종텔레콤": ["세종텔레콤", "스노우맨"],
            "큰사람": ["큰사람", "이야기모바일"]
        }
        # 제목에 업체명이 있는지 검사
        for name, kws in small_map.items():
            if any(k in t for k in kws): return [{"name": name}]
        return None  # 업체명이 없으면 아예 수집하지 않음
    
    return None

def post_notion(db_id, title, link, tags, pub_date):
    """제목에 하이퍼링크를 걸어 노션에 저장"""
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
    
    seen_urls = set()
    seen_titles = [] 

    for keywords, limit, default_tag in configs:
        tag_count = 0 
        print(f"🔍 {db_key} - {default_tag} 작업 중...")
        
        query = " ".join(keywords)
        # 검색은 최신순으로 한 번만
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort=date"
        res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code != 200: continue
        raw_items = res.json().get('items', [])

        for item in raw_items:
            if tag_count >= 12: break # 태그당 최대 12개 제한
            if item['link'] in seen_urls: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 1. 주제 중복 제거 (유사도 45% 초과 시 패스)
            is_duplicate_topic = False
            for seen_title in seen_titles:
                if get_similarity(title, seen_title) > 0.45:
                    is_duplicate_topic = True
                    break
            if is_duplicate_topic: continue

            # 2. 태그 및 업체명 매칭 (업체명 없으면 None 반환됨)
            tags = get_final_tags(title, db_key, default_tag)
            
            if tags:
                # MNO는 태그 일관성 유지
                if db_key == "MNO" and tags[0]['name'] != default_tag: continue
                
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                
                # 기간 내 기사거나, 데이터 확보를 위한 최소 2개 수집
                if p_date in allowed_dates or (db_key != "MNO" and tag_count < 2):
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        seen_urls.add(item['link'])
                        seen_titles.append(title)
                        tag_count += 1

if __name__ == "__main__":
    # 각 DB별 수집 설정
    collect("SUBSID", [
        (["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"),
        (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")
    ], 60)
    
    collect("MNO", [
        (["통신3사", "통신업계", "통신주"], 12, "통신 3사"),
        (["SK텔레콤", "SKT"], 12, "SKT"), (["KT"], 12, "KT"), (["LG유플러스"], 12, "LG U+")
    ], 7)
    
    collect("FIN", [(["토스모바일", "리브모바일", "우리원모바일"], 12, "금융권")], 60)
    
    # [중소 사업자] 단순히 '알뜰폰'으로 검색하되, 필터에서 지정 업체명만 걸러냄
    collect("SMALL", [
        (["아이즈모바일"], 12, "아이즈모바일"), (["프리텔레콤"], 12, "프리모바일"),
        (["에넥스텔레콤"], 12, "에넥스텔레콤"), (["유니컴즈"], 12, "유니컴즈"),
        (["인스코비", "프리티"], 12, "인스코비"), (["세종텔레콤"], 12, "세종텔레콤"),
        (["큰사람", "이야기모바일"], 12, "큰사람")
    ], 60)
