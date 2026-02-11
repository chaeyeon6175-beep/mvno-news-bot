import os, requests, re
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse

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

def clean_id(raw_id):
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def clean_url(url):
    """URL에서 파라미터를 제거하여 중복 체크의 정확도를 높임"""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def get_article_info(url):
    try:
        res = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=5)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        content = ""
        for selector in ['div#articleBodyContents', 'div#articleBody', 'article', 'div.content']:
            target = soup.select_one(selector)
            if target:
                content = target.get_text(strip=True)
                break
        if not content: content = "본문 내용을 가져올 수 없습니다."
        img_tag = soup.find('meta', property='og:image')
        img = img_tag['content'] if img_tag else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000"
        return {"img": img, "summary": content[:120].replace("\n", " ").strip() + "..."}
    except:
        return {"img": "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000", "summary": "요약 실패"}

def post_notion(db_id, title, link, img, summary, tag):
    target_id = clean_id(db_id)
    if not target_id: return
    today_str = datetime.now().strftime('%Y-%m-%d')
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"rich_text": [{"text": {"content": today_str}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    res = requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)
    if res.status_code == 200:
        print(f"      ✅ [{tag}] 전송 성공: {title[:15]}...")
    else:
        print(f"      ❌ 전송 실패: {res.json().get('message')}")

def collect_news(queries, limit, db_id, tag_name, processed_links):
    if not db_id: return
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    url = f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=30&sort=sim"
    res = requests.get(url, headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        items = res.json().get('items', [])
        count = 0
        for item in items:
            if count >= limit: break
            
            # 링크 정제 및 중복 검사
            raw_link = item['originallink'] or item['link']
            link = clean_url(raw_link)
            
            if link in processed_links:
                continue # 이미 처리된 링크는 건너뜀
                
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            info = get_article_info(link)
            post_notion(db_id, title, link, info['img'], info['summary'], tag_name)
            
            processed_links.add(link) # 처리된 링크 저장
            count += 1

if __name__ == "__main__":
    # 프로그램 실행 시 중복 링크를 기억할 세트
    global_processed_links = set()

    configs = [
        # 1. MNO
        (["통신 3사", "이통3사"], 5, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 5, DB_IDS["MNO"], "SKT"),
        (["KT", "케이티"], 5, DB_IDS["MNO"], "KT"),
        (["LG유플러스", "LGU+"], 5, DB_IDS["MNO"], "LG U+"),
        # 2. 자회사 (SUBSID)
        (["SK텔링크", "세븐모바일"], 3, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일", "KT엠모바일"], 3, DB_IDS["SUBSID"], "KT M모바일"),
        (["KT스카이라이프"], 3, DB_IDS["SUBSID"], "KT스카이라이프"),
        (["LG헬로비전", "헬로모바일"], 3, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 3, DB_IDS["SUBSID"], "미디어로그"),
        # 3. 금융권 (FIN)
        (["KB리브모바일", "리브엠"], 3, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 3, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 3, DB_IDS["FIN"], "우리원모바일"),
        # 4. 중소 알뜰폰 (SMALL)
        (["아이즈모바일"], 2, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤", "프리모바일"], 2, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤", "A모바일"], 2, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 2, DB_IDS["SMALL"], "인스모바일")
    ]
    
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag, global_processed_links)
