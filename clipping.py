import os, requests

TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID = os.environ.get('NOTION_DB_ID')

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

data = {
    "parent": {"database_id": DB_ID},
    "properties": {
        "제목": {"title": [{"text": {"content": "연결 테스트 성공!"}}]},
        "분류": {"multi_select": [{"name": "SK텔링크"}]},
        "링크": {"url": "https://naver.com"},
        "날짜": {"rich_text": [{"text": {"content": "2024-01-01"}}]}
    }
}

res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=data)
print(f"응답 결과: {res.status_code}") # 200이 나오면 성공
print(res.text)
