"""법원경매정보(courtauction.go.kr) 스크래핑 — 기본 비활성화.

대법원 법원경매정보는 공식 오픈API가 없다. 게다가 2026-08-03
`court_auction_diagnostic.py`를 GitHub Actions에서 실행해 확인한 결과,
courtauction.go.kr은 헤더/봇 감지 수준이 아니라 **네트워크 레벨에서 해외
클라우드 IP 대역 자체를 차단**하고 있다 (HTTP 응답조차 없이 TCP 연결
단계에서 `ConnectTimeout` 발생). 즉:

- User-Agent 위장, Selenium/Playwright 등 클라이언트 사이드 우회로는 해결되지
  않는다 — 애초에 패킷이 도달하지 못한다.
- GitHub Actions(해외 리전)에서는 이 모듈을 절대 구현/실행할 수 없다.
- 국내 리전 서버(AWS 서울 리전, 네이버클라우드, 국내 VPS 등)에서 접속이
  되는지부터 별도로 검증이 필요하다. 그마저 안 되면 지지옥션·굿옥션·탱크옥션
  같은 민간 유료 API로 전환하는 수밖에 없다.

이 모듈을 실제로 구현하게 되면 추가로 확인할 것:

1. courtauction.go.kr의 이용약관과 robots.txt를 검토해 스크래핑이 허용되는
   범위인지 확인한다.
2. 요청 빈도를 낮게 유지하고 (예: 검색당 수 초 간격), 캐싱해서 동일 조건을
   반복 조회하지 않는다.
3. 사이트 구조 변경에 취약하므로 실패를 조용히 삼키지 말고 알림을 남긴다.

`ENABLE_COURT_SCRAPING=true`로 설정하지 않는 한 `search_court_auction`은
아무 데이터도 반환하지 않는다.
"""

from typing import List, Optional

from .config import ENABLE_COURT_SCRAPING
from .models import AuctionItem


def search_court_auction(
    property_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    budget_max: Optional[int] = None,
) -> List[AuctionItem]:
    if not ENABLE_COURT_SCRAPING:
        return []

    raise NotImplementedError(
        "법원경매정보 스크래핑은 아직 구현되지 않았습니다. "
        "DESIGN.md 2.2절의 법적 검토를 마친 뒤 이 함수를 구현하세요."
    )
