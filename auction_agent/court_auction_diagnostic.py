"""법원경매정보(courtauction.go.kr) 스크래핑 가능 여부를 확인하는 진단 스크립트.

공식 API가 없어서 사이트 접근 자체가 되는지, 봇 차단(WAF)이 있는지부터
GitHub Actions(실제 인터넷 접근)에서 확인한다. 이 스크립트는 실 서비스 코드가
아니라 조사용이며, 결과를 보고 court_auction_source.py 구현 여부/방식을
결정한다.
"""

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

URLS = [
    "https://www.courtauction.go.kr/",
    "https://www.courtauction.go.kr/robots.txt",
    "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ159M00.xml",
]


def main() -> None:
    session = requests.Session()
    session.headers.update(HEADERS)

    for url in URLS:
        print(f"=== GET {url} ===")
        try:
            resp = session.get(url, timeout=15)
            print(f"status: {resp.status_code}")
            print(f"cookies: {list(session.cookies.keys())}")
            print(f"본문 앞 500자:\n{resp.text[:500]}")
        except Exception as e:
            print(f"요청 실패: {e}")
        print()


if __name__ == "__main__":
    main()
