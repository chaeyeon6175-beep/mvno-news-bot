import os, requests, re, time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# 1. 환경 변수 및 설정 (기존과 동일)
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
    exclude = ["야구", "배구", "농구", "축구", "스포츠", "쇼핑", "이커머스", "11번가", "주가", "증시", "상장", "음악회", "전시회", "인사", "동정"]
    if any(ex in t for ex in exclude): return False
    include = ["요금제", "알뜰폰", "mvno", "5g", "6g", "lte", "통신", "가입자", "단말기", "네트워크", "유심", "esim", "로밍", "결합", "공시지원", "알뜰폰"]
    return any(inc in t for inc in include)

def get_final_tags(title, db_key, default_tag):
    if not is_telecom_industry_news(title): return None
    t = title.lower().replace(' ', '')
    if any(ex in t for ex in ["sk쉴더스", "지니뮤직", "kt알파"]): return None

    # 1. MNO DB (통신3사 본업)
    if db_key == "MNO":
        if any(x in t for x in ["텔링크", "엠모바일", "헬로비전", "스카이라이프", "미디어로그", "리브m", "리브모바일", "토스모바일", "우리원"]): return None
        sa3_keywords = ["통신3사", "이통3사", "통신업계", "통신주", "이통사공통", "3사"]
        skt, kt, lg = any(x in t for x in ["skt", "sk텔레콤"]), any(x in t for x in ["kt", "케이티"]), any(x in t for x in ["lgu+", "lg유플러스"])
        if any(x in t for x in sa3_keywords) or (skt + kt + lg >= 2): return [{"name": "통신 3사"}]
        elif skt: return [{"name": "SKT"}]
        elif kt: return [{"name": "KT"}]
        elif lg: return [{"name": "LG U+"}]
        return [{"name": default_tag}]

    # 2. 금융 DB (FIN) - 수집 안되던 문제 해결을 위해 키워드 대폭 확장
    elif db_key == "FIN":
        fin_map = {
            "토스모바일": ["토스모바일", "토스알뜰폰"],
            "우리원모바일": ["우리원모바일", "우리은행알뜰폰", "우리원알뜰폰"],
            "KB리브모바일": ["리브모바일", "리브m", "kb알뜰폰", "국민은행알뜰폰"]
        }
        for name, kws in fin_map.items():
            if any(k in t for k in kws): return [{"name": name}]
        return None

    # 3. 자회사 DB (SUBSID)
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

def collect(db_key, configs, days):
    db_id = DB_IDS.get(db_key)
    if not db_id: return
    allowed_dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days + 1)]
    
    seen_urls = set()
    seen_titles = [] 

    for keywords, limit, default_tag in configs:
        tag_count = 0 
        print(f"🔍 {db_key} - {default_tag} 수집 시도 중...")
        
        query = " ".join(keywords)
        raw_items = []
        for sort_type in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort_type}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200:
                raw_items.extend(res.json().get('items', []))

        # URL 기준 중복 제거
        unique_raw_items = []
        temp_urls = set()
        for item in raw_items:
            if item['link'] not in temp_urls:
                unique_raw_items.append(item)
                temp_urls.add(item['link'])

        for item in unique_raw_items:
            if tag_count >= 12: break 
            if item['link'] in seen_urls: continue

            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # 주제 중복 제거
            is_duplicate = False
            for st in seen_titles:
                if get_similarity(title, st) > 0.45:
                    is_duplicate = True; break
            if is_duplicate: continue

            tags = get_final_tags(title, db_key, default_tag)
            if tags:
                # MNO 전용 태그 필터
                if db_key == "MNO" and tags[0]['name'] != default_tag: continue
                
                p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
                
                # 금융권 수집 확률을 높이기 위해 기간 및 최소 수량 조건 적용
                if p_date in allowed_dates or (tag_count < 2):
                    if post_notion(db_id, title, item['link'], tags, p_date):
                        seen_urls.add(item['link'])
                        seen_titles.append(title)
                        tag_count += 1
        print(f"✅ {db_key} - {default_tag}: {tag_count}개 수집 완료")

if __name__ == "__main__":
    # 3번 DB (금융권): 30일치로 범위 확대
    collect("FIN", [
        (["토스모바일"], 12, "토스모바일"), 
        (["리브모바일", "리브M"], 12, "KB리브모바일"), 
        (["우리원모바일", "우리은행 알뜰폰"], 12, "우리원모바일")
    ], 30)

    # 1번 DB (MNO)
    collect("MNO", [
        (["통신3사", "통신업계"], 12, "통신 3사"),
        (["SK텔레콤", "SKT"], 12, "SKT"), (["KT"], 12, "KT"), (["LG유플러스"], 12, "LG U+")
    ], 30)

    # 2번 DB (자회사)
    collect("SUBSID", [
        (["SK텔링크"], 12, "SK텔링크"), (["KT엠모바일"], 12, "KT M모바일"),
        (["LG헬로비전"], 12, "LG헬로비전"), (["스카이라이프"], 12, "KT스카이라이프"), (["미디어로그"], 12, "미디어로그")
    ], 60)
