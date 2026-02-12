name: News Clipping Automation

on:
  schedule:
    # 한국 시간 오전 9시 30분 (UTC 00:30)
    - cron: '30 0 * * *'
  workflow_dispatch: # 지금 즉시 수집하고 싶을 때 사용하는 수동 버튼

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install requests beautifulsoup4

      - name: Run news clipping script
        env:
          NAVER_CLIENT_ID: ${{ secrets.NAVER_CLIENT_ID }}
          NAVER_CLIENT_SECRET: ${{ secrets.NAVER_CLIENT_SECRET }}
          NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
          DB_ID_MNO: ${{ secrets.DB_ID_MNO }}
          DB_ID_SUBSID: ${{ secrets.DB_ID_SUBSID }}
          DB_ID_FIN: ${{ secrets.DB_ID_FIN }}
          DB_ID_SMALL: ${{ secrets.DB_ID_SMALL }}
        run: python clipping.py
