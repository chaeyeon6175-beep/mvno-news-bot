import os, requests, json

# 환경 변수 로드
NOTION_TOKEN = os.environ.get('NOTION_TOKEN')
DB_ID = os.environ.get('DB_ID_SUBSID') # 자회사 ID 테스트

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def diagnose():
    # 1. 봇 정보 확인 (어느 워크스페이스 소속인지)
    print("🔍 1. 봇 정보 확인 중...")
    me_res = requests.get("https://api.notion.com/v1/users/me", headers=HEADERS)
    if me_res.status_code == 200:
        me_data = me_res.json()
        print(f"   ✅ 성공! 봇 이름: {me_data.get('name')}")
        print(f"   🏢 소속 워크스페이스 ID: {me_data.get('bot', {}).get('workspace_name', '알 수 없음')}")
    else:
        print(f"   ❌ 봇 정보 가져오기 실패: {me_res.text}")
        return

    # 2. 데이터베이스 접근 확인
    target_id = DB_ID.replace("-", "").strip()
    print(f"\n🔍 2. 데이터베이스({target_id}) 접근 확인 중...")
    db_res = requests.get(f"https://api.notion.com/v1/databases/{target_id}", headers=HEADERS)
    
    if db_res.status_code == 200:
        print("   ✅ 축하합니다! 데이터베이스 연결에 성공했습니다.")
        print(f"   📋 DB 제목: {db_res.json().get('title', [{}])[0].get('plain_text', '제목없음')}")
    elif db_res.status_code == 404:
        print("   ❌ 404 에러: 이 봇은 해당 DB를 찾을 수 없습니다.")
        print("      👉 해결책: 페이지 우측 상단 '...' -> '연결 추가'에서 이 봇이 정말 추가되어 있는지 다시 보세요.")
    else:
        print(f"   ❌ 기타 오류 ({db_res.status_code}): {db_res.text}")

if __name__ == "__main__":
    diagnose()
