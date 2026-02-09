import os, requests
from datetime import datetime
from bs4 import BeautifulSoup

# 환경 변수 로드
NAVER_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID_MNO = os.environ.get('DB_ID_MNO')
DB_ID_SUBSID = os.environ.get('DB_ID_SUBSID')
DB_ID_FIN = os.environ.get('DB_ID_FIN')
DB_ID_SMALL = os.environ.get('DB_ID_SMALL')

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def clear_database(db_id):
    query_url = f"https://api.notion.com/v1/databases/{db_id}/query"
    res = requests.post(query_url, headers=HEADERS)
    if res.status_code == 200:
        for page in res.json().get("results", []):
            requests.patch(f"https://api.notion.com/v1/pages/{page['id']}", headers=HEADERS, json={"archived": True})

def get_img(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        img = soup.find('meta', property='og:image')
        return img['content'] if img else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
    except:
        return "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"

def post_notion(db_id, title, link, date_str, img, tag=None):
    clean_date = datetime.now().strftime('%Y년 %m월 %d일')
    props = {
        "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
        "날짜": {"rich_text": [{"text": {"content": clean_date}}]},
        "링크": {"url": link}
    }
    if tag:
        props["분류"] = {"multi_select": [{"name": tag}]}
        
    data = {"parent": {"database_id": db_id}, "cover": {"type": "external", "external": {"url": img}}, "properties": props}
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def crawl_and_post(kw_list, db_id, category_map=None, strict=False):
    seen_titles = set()
    final_count = 0
    
    for kw in kw_list:
        if final_count >= 15: break # 각 DB당 최대 15개 내외 조절
        
        # 정확도를 높이기 위해 검색어에 쌍따옴표 추가 (네이버 상세검색 기능)
        search_query = f'"{kw}"'
        res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=30&sort=date", 
                           headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
        
        if res.status_code == 200:
            for item in res.json().get('items', []):
                title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
                
                # [필터링 로직] 제목에 키워드가 실제로 포함되어 있는지 확인 (strict 모드)
                if strict and not any(k.lower() in title.lower() for k in [kw]):
                    continue
                
                if title[:15] not in seen_titles:
                    seen_titles.add(title[:15])
                    
                    # [MNO 특수 분류]
                    tag = None
                    if category_map:
                        # 통신3사 통합 키워드 우선 체크
                        if any(x in title for x in ["통신 3사", "통신3사", "이통3사", "SKT·KT·LGU+"]):
                            tag = "통신 3사"
                        else:
                            tag = category_map.get(kw, "기타")
                    
                    img = get_img(item['originallink'] or item['link'])
                    post_notion(db_id, title, item['originallink'] or item['link'], item['pubDate'], img, tag)
                    final_count += 1
                if final_count >= 15: break

if __name__ == "__main__":
    for d_id in [DB_ID_MNO, DB_ID_SUBSID, DB_ID_FIN, DB_ID_SMALL]:
        if d_id: clear_database(d_id)

    # 1. MNO 시장 (태그 맵핑)
    mno_map = {"SKT":"SKT", "SK텔레콤":"SKT", "KT":"KT", "LG U+":"LGU+", "LG유플러스":"LGU+"}
    crawl_and_post(list(mno_map.keys()), DB_ID_MNO, category_map=mno_map, strict=True)

    # 2. MVNO 자회사 (정확히 제목에 있는 것만)
    subsid_kws = ["SK텔링크", "KT M모바일", "KT 엠모바일", "KT스카이라이프", "LG헬로비전", "미디어로그", "에스케이 SK텔링크"]
    crawl_and_post(subsid_kws, DB_ID_SUBSID, strict=True)

    # 3. MVNO 금융
    fin_kws = ["KB 리브모바일", "토스모바일", "우리원모바일"]
    crawl_and_post(fin_kws, DB_ID_FIN, strict=True)

    # 4. 중소사업자 (키워드 구체화하여 오인 수집 방지)
    small_kws = ["아이즈모바일", "프리텔레콤", "에넥스텔레콤", "모바일실용주의", "헬로모바일"]
    crawl_and_post(small_kws, DB_ID_SMALL, strict=True)
