"""법원경매정보(courtauction.go.kr) 스크래핑 — 기본 비활성화.

대법원 법원경매정보는 공식 오픈API가 없다. 이 모듈을 활성화하기 전에
반드시 다음을 확인하자:

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
