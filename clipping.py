# main 함수 하단의 수집 범위를 1일 -> 3일로 조정
if __name__ == "__main__":
    for key in DB_IDS: clear_notion_database(DB_IDS[key])
    titles = set()
    
    # SUBSID(자회사)는 60일 유지
    collect_news("SUBSID", [...], titles, 60)
    
    # [수정] MNO 기사 범위를 3일로 확대하여 '기사 없음' 방지
    collect_news("MNO", [
        (["SK텔레콤", "SKT"], 20, "SKT"), 
        (["KT", "케이티"], 10, "KT"),
        (["LG유플러스"], 10, "LG U+"),
        (["통신사"], 5, "통신 3사")
    ], titles, 3) # 1에서 3으로 변경
