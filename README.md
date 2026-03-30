# MVNO 뉴스 브리핑 봇

네이버 뉴스 API로 MVNO(알뜰폰) 관련 기사를 수집하고, 키워드 기반 영향도를 분석하여 Notion 데이터베이스에 자동 저장하는 봇입니다.

## 주요 기능

- **네이버 뉴스 검색** — 통신사/MVNO 키워드별 뉴스 자동 수집
- **키워드 기반 영향도 분석** — 기사 제목에서 키워드를 매칭하여 3단계로 분류
  - 🔴 중요: 도매대가, 규제/정책, 요금제 경쟁, 망 품질
  - 🟡 모니터링: 단말 출시, MNO 마케팅, 가입자/점유율, 결합상품, 실적
  - 🟢 참고: 일반 동향
- **중복 제거** — 문자열 유사도 + 단어 겹침 기반 중복 기사 필터링
- **Notion 자동 저장** — 영향도, 영향도 이유 컬럼 포함

## 수집 대상

| 카테고리 | 대상 | 수집 기간 |
|---------|------|----------|
| MNO | SKT, KT, LGU+, 통신 3사 | 최근 5일 |
| MVNO 자회사 | SK텔링크, KT M모바일, LG헬로비전, KT스카이라이프, 미디어로그 | 최근 30일 |
| MVNO 금융 | 토스모바일, KB리브모바일, 우리원모바일 | 최근 60일 |
| 중소사업자 | 아이즈모바일, 프리모바일, 에넥스텔레콤, 유니컴즈, 인스코비, 세종텔레콤, 큰사람 | 최근 60일 |

## 실행 환경

### 환경 변수 (.env)

```
NAVER_CLIENT_ID=네이버_API_클라이언트_ID
NAVER_CLIENT_SECRET=네이버_API_클라이언트_시크릿
NOTION_TOKEN=노션_API_토큰
DB_ID_MNO=노션_DB_ID
DB_ID_SUBSID=노션_DB_ID
DB_ID_FIN=노션_DB_ID
DB_ID_SMALL=노션_DB_ID
```

### 로컬 실행

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python clipping.py
```

### GitHub Actions (자동 실행)

매일 오전 10시(KST)에 자동 실행됩니다. GitHub Secrets에 환경 변수를 등록해야 합니다.

## Notion 데이터베이스 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| 제목 | Title | 기사 제목 (링크 포함) |
| 날짜 | Rich text | 기사 발행일 |
| 링크 | URL | 기사 원문 링크 |
| 분류 | Multi-select | 통신사/업체 분류 태그 |
| 영향도 | Select | 🔴 중요 / 🟡 모니터링 / 🟢 참고 |
| 영향도 이유 | Rich text | 영향도 판단 근거 |
