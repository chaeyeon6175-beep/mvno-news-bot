import os, requests, re, time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

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

def clear_notion_database(db_id):
    if not db_id: return
    target_id = re.sub(r'[^a-fA-F0-9]', '', db_id)
    try:
        res = requests.post(f"https://api.notion.com/v1/databases/{target_id}/query", headers=HEADERS)
        if res.status_code == 200:
            pages = res.json().get("results", [])
            for page in pages:
                requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})
    except: pass

def get_smart_tags(title):
    """제목 분석을 통한 정밀 다중 태그 추출"""
    t = title.lower().replace(' ', '')
    tags = []
    if any(x in t for x in ["통신3사", "이통3사", "이통사", "통신사공통"]): tags.append("통신 3사")
    if any(x in t for x in ["sk텔레콤", "skt"]): tags.append("SKT")
    if any(x in t for x in ["kt", "케이티"]): tags.append("KT")
    if any(x in t for x in ["lg유플러스", "lgu+", "엘지유플러스"]): tags.append("LG U+")
    if any(x in t for x in ["sk텔링크", "7모바일", "세븐모바일"]): tags.append("SK텔링크")
    if any(x in t for x in ["ktm모바일", "kt엠모바일"]): tags.append("KT M모바일")
    if any(x in t for x in ["리브모바일", "리브m", "토스모바일", "금융권"]): tags.append("금융권")
    if not tags: tags.append("알뜰폰 일반")
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
    print(f"\n🔍 {db_key} 데이터베이스 수집 중...")

    for keywords, limit, default_tag in configs:
        # 키워드별 상한선 12개 제한 (기존 설정값이 12보다 크면 12로 고정)
        real_limit = min(limit, 12)
        query = " ".join(keywords)
        
        # 최신순과 관련도순을 조합하여 데이터 확보
        items = []
        for sort_type in ["date", "sim"]:
            url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=100&sort={sort_type}"
            res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
            if res.status_code == 200:
                items.extend(res.json().get('items', []))
            if len(items) > 0: break

        count = 0
        for item in items:
            p_date = datetime.strptime(item['pubDate'], '%a, %d %b %Y %H:%M:%S +0900').strftime('%Y-%m-%d')
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            
            # [수정] 자회사(SUBSID), 금융(FIN), 중소(SMALL)는 기사가 없으면 날짜 무시하고 최소 2개 보장
            is_min_guaranteed = (db_key in ["SUBSID", "FIN", "SMALL"]) and (count < 2)
            
            if p_date in allowed_dates or is_min_guaranteed:
                smart_tags = get_smart_tags(title)
                if post_notion(db_id, title, item['link'], smart_tags, p_date):
                    count += 1
                    print(f"      ✅ [{default_tag}] 등록: {title[:20]}... ({p_date})")
            
            if count >= real_limit: break
        
        if count == 0:
            print(f"   ⚠️ {default_tag}: 조건에 맞는 기사가 없습니다.")

if __name__ == "__main__":
    if not NAVER_ID:
        print("❌ 네이버 API 키를 확인하세요.")
    else:
        for k in DB_IDS: clear_notion_database(DB_IDS[k])
        
        # 1. 자회사 (60일 범위, 최소 2개 보장, 최대 12개)
        collect("SUBSID", [
            (["SK텔링크", "7모바일", "세븐모바일"], 12, "SK텔링크"),
            (["KT M모바일", "KT엠모바일"], 12, "KT M모바일"),
            (["헬로모바일", "LG헬로비전"], 12, "LG헬로비전")
        ], 60)

        # 2. MNO (7일 범위, 최대 12개)
        collect("MNO", [
            (["SK텔레콤", "SKT"], 12, "SKT"),
            (["KT", "케이티"], 12, "KT"),
            (["LG유플러스", "LGU+"], 12, "LG U+"),
            (["통신3사", "이통3사", "통신사"], 12, "통신 3사")
        ], 7)

        # 3. 금융/중소 (60일 범위, 최소 2개 보장, 최대 12개)
        collect("FIN", [(["리브모바일", "토스모바일", "우리원모바일"], 12, "금융권")], 60)
        collect("SMALL", [(["중소 알뜰폰", "알뜰폰 이벤트"], 12, "중소 알뜰폰")], 60)

    print("\n🏁 모든 수집 및 제한 설정 완료")
