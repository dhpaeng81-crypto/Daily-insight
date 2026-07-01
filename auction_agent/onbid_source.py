"""온비드 공매 물건 조회 (공식 공공데이터포털 API, PublicDataReader.Kamco 래핑).

서비스/기능/필드명은 로컬에 설치된 PublicDataReader==1.1.1-post2의
`Kamco.meta_dict`와 내부 컬럼 번역 테이블을 직접 확인해서 검증했다
(`통합용도별물건목록` = 아파트/주택/상가/토지 등 모든 용도를 포괄하는 목록 API).

다만 이 실행 환경은 `openapi.onbid.co.kr`로 나가는 아웃바운드가 네트워크
정책상 차단되어 있어 실제 응답을 받아 재확인하지는 못했다. `ONBID_SERVICE_KEY`
발급 후 처음 실행할 때 아래 필드 매핑이 실제 응답과 다르면 `_row_to_item`을
조정해야 한다.
"""

from typing import List, Optional

from .config import ONBID_SERVICE_KEY
from .models import AuctionItem

_FUNC_GROUP = "물건정보"
_FUNC_NAME = "통합용도별물건목록"  # getUnifyUsageCltr


def _get_client():
    if not ONBID_SERVICE_KEY:
        raise RuntimeError(
            "ONBID_SERVICE_KEY가 설정되어 있지 않습니다. "
            "auction_agent/README.md의 키 발급 안내를 참고하세요."
        )
    import PublicDataReader as pdr

    return pdr.Kamco(ONBID_SERVICE_KEY)


def _to_int(value) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return 0


def _split_region(address: str):
    parts = address.split()
    sido = parts[0] if len(parts) > 0 else ""
    sigungu = parts[1] if len(parts) > 1 else ""
    return sido, sigungu


def _row_to_item(row: dict) -> AuctionItem:
    """온비드 `통합용도별물건목록` 응답 1건을 공통 스키마로 변환 (translate=False, 원본 코드 기준)."""

    address = str(row.get("LDNM_ADRS") or row.get("NMRD_ADRS") or "")
    sido, sigungu = _split_region(address)

    return AuctionItem(
        source="onbid",
        item_id=str(row.get("CLTR_NO") or row.get("PBCT_NO") or ""),
        title=str(row.get("CLTR_NM") or "(제목 없음)"),
        property_type=str(row.get("CTGR_FULL_NM") or "기타"),
        region_sido=sido,
        region_sigungu=sigungu,
        address=address,
        appraisal_price=_to_int(row.get("APSL_ASES_AVG_AMT")),
        min_bid_price=_to_int(row.get("MIN_BID_PRC")),
        bid_start_date=row.get("PBCT_BEGN_DTM") or None,
        bid_end_date=row.get("PBCT_CLS_DTM") or None,
        source_url="https://www.onbid.co.kr",
        failed_count=_to_int(row.get("USCBD_CNT")),
        status=str(row.get("PBCT_CLTR_STAT_NM") or "진행중"),
    )


def search_onbid(
    property_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    budget_max: Optional[int] = None,
) -> List[AuctionItem]:
    """조건에 맞는 온비드 공매 물건을 조회한다.

    property_types: 예) ["아파트", "주택"]
    regions: 예) ["서울특별시 강남구"]
    budget_max: 최저입찰가 상한 (원)

    현재는 API가 지원하는 서버 사이드 검색 파라미터(용도/지역 코드)를 확정하지
    못해 전체 목록을 가져온 뒤 클라이언트에서 필터링한다. 물건 수가 많아지면
    온비드코드 조회서비스로 용도/주소 코드를 먼저 얻어 서버 사이드로 필터링하도록
    개선하자.
    """
    client = _get_client()
    df = client.get_data(_FUNC_GROUP, _FUNC_NAME, translate=False)

    if df is None or df.empty:
        return []

    items = [_row_to_item(row) for row in df.to_dict("records")]

    if property_types:
        items = [i for i in items if any(pt in i.property_type for pt in property_types)]
    if regions:
        items = [
            i for i in items
            if any(r in f"{i.region_sido} {i.region_sigungu}" for r in regions)
        ]
    if budget_max:
        items = [i for i in items if i.min_bid_price and i.min_bid_price <= budget_max]

    return items
