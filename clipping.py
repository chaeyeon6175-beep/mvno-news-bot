import os, requests, re
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
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

def clean_id(raw_id):
    if not raw_id: return ""
    return re.sub(r'[^a-fA-F0-9]', '', raw_id)

def clean_url(url):
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def is_similar(title1, title2):
    """제목 간의 유사도를 측정하여 8글자 이상 겹치거나 유사도가 높으면 True 반환"""
    # 공백 및 특수문자 제거 후 비교
    t1 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title1)
    t2 = re.sub(r'[^가-힣a-zA-Z0-9]', '', title2)
    
    # 1. 가장 긴 공통 부분 문자열 확인 (8글자 기준)
    match = SequenceMatcher(None, t1, t2).find_longest_match(0, len(t1), 0, len(t2))
    if match.size >= 8:
        return True
    
    # 2. 전체적인 유사도 비율 확인 (80% 이상 유사 시 중복 간주)
    if SequenceMatcher(None, t1, t2).ratio() > 0.8:
        return True
        
    return False

def get_article_info(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        res = requests.get(url, headers=headers, timeout=8)
        res.encoding = 'utf-8'
        if res.status_code != 200: return None

        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 소제목 추출 시도
        sub_title = ""
        for selector in ['div.sub_title', 'strong.sub_title', 'h3.sub_title', 'div.article_summary', 'p.summary']:
            target = soup.select_one(selector)
            if target and target.get_text(strip=True):
                sub_title = target.get_text(strip=True)
                break
        
        if not sub_title:
            for selector in ['div#articleBodyContents', 'div#dic_area', 'div#articleBody', 'article']:
                target = soup.select_one(selector)
                if target:
                    content = target.get_text(" ", strip=True)
                    content = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '', content)
                    sub_title = content[:150].strip() + "..."
                    break
        
        return {"img": soup.find('meta', property='og:image')['content'] if soup.find('meta', property='og:image') else "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000", "summary": sub_title or "요약 없음"}
    except:
        return None

def post_notion(db_id, title, link, img, summary, tag):
    target_id = clean_id(db_id)
    if not target_id: return
    data = {
        "parent": {"database_id": target_id},
        "cover": {"type": "external", "external": {"url": img}},
        "properties": {
            "제목": {"title": [{"text": {"content": title, "link": {"url": link}}}]},
            "소제목": {"rich_text": [{"text": {"content": summary}}]},
            "날짜": {"rich_text": [{"text": {"content": datetime.now().strftime('%Y-%m-%d')}}]},
            "링크": {"url": link},
            "분류": {"multi_select": [{"name": tag}]}
        }
    }
    requests.post("https://api.notion.com/v1/pages", headers=HEADERS, json=data)

def collect_news(queries, limit, db_id, tag_name, processed_links, processed_titles):
    if not db_id: return
    search_query = " | ".join([f"\"{q}\"" for q in queries])
    res = requests.get(f"https://openapi.naver.com/v1/search/news.json?query={search_query}&display=50&sort=sim", 
                       headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET})
    
    if res.status_code == 200:
        print(f"\n▶ [{tag_name}] 수집 시작")
        items = res.json().get('items', [])
        count = 0
        for item in items:
            if count >= limit: break
            
            title = item['title'].replace('<b>','').replace('</b>','').replace('&quot;','"')
            link = clean_url(item['originallink'] or item['link'])
            
            # URL 중복 및 제목 유사도 중복 체크
            if link in processed_links: continue
            if any(is_similar(title, prev_title) for prev_title in processed_titles): continue
            
            info = get_article_info(link)
            if info is None: continue # 링크 오류 시 스킵
                
            post_notion(db_id, title, link, info['img'], info['summary'], tag_name)
            processed_links.add(link)
            processed_titles.add(title)
            print(f"      ✅ 전송 성공: {title[:15]}...")
            count += 1

if __name__ == "__main__":
    links, titles = set(), set()
    configs = [
        (["통신 3사", "이통3사"], 5, DB_IDS["MNO"], "통신 3사"),
        (["SK텔레콤", "SKT"], 5, DB_IDS["MNO"], "SKT"),
        (["KT"], 5, DB_IDS["MNO"], "KT"),
        (["LG유플러스"], 5, DB_IDS["MNO"], "LG U+"),
        (["SK텔링크", "세븐모바일"], 3, DB_IDS["SUBSID"], "SK텔링크"),
        (["KT M모바일"], 3, DB_IDS["SUBSID"], "KT M모바일"),
        (["LG헬로비전"], 3, DB_IDS["SUBSID"], "LG헬로비전"),
        (["미디어로그", "유모바일"], 3, DB_IDS["SUBSID"], "미디어로그"),
        (["KB리브모바일"], 3, DB_IDS["FIN"], "KB 리브모바일"),
        (["토스모바일"], 3, DB_IDS["FIN"], "토스모바일"),
        (["우리원모바일"], 3, DB_IDS["FIN"], "우리원모바일"),
        (["아이즈모바일"], 2, DB_IDS["SMALL"], "아이즈모바일"),
        (["프리텔레콤"], 2, DB_IDS["SMALL"], "프리텔레콤"),
        (["에넥스텔레콤"], 2, DB_IDS["SMALL"], "에넥스텔레콤"),
        (["인스모바일"], 2, DB_IDS["SMALL"], "인스모바일")
    ]
    for qs, lim, d_id, tag in configs:
        collect_news(qs, lim, d_id, tag, links, titles)
