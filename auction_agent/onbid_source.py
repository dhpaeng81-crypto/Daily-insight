"""온비드 공매 물건 조회 (공식 공공데이터포털 API).

PublicDataReader의 Kamco 모듈을 얇게 감싼다. 실제 서비스/함수 조합은
`PublicDataReader.Kamco(serviceKey).meta_dict`로 확인하고 이 모듈의
`_FUNC_GROUP`/`_FUNC_NAME`을 실제 값으로 맞춰야 한다 (라이브러리 버전에 따라
서비스명이 바뀔 수 있음).
"""

from typing import List, Optional

from .config import ONBID_SERVICE_KEY
from .models import AuctionItem

_FUNC_GROUP = "부동산 물건목록 조회"
_FUNC_NAME = "물건목록"


def _get_client():
    if not ONBID_SERVICE_KEY:
        raise RuntimeError(
            "ONBID_SERVICE_KEY가 설정되어 있지 않습니다. "
            "auction_agent/README.md의 키 발급 안내를 참고하세요."
        )
    import PublicDataReader as pdr

    return pdr.Kamco(ONBID_SERVICE_KEY)


def _row_to_item(row: dict) -> AuctionItem:
    """온비드 API 응답 1건을 공통 스키마로 변환.

    실제 필드명은 승인받은 서비스의 응답 스펙(data.go.kr 문서)에 맞춰
    조정해야 한다. 대표적으로 쓰이는 키 이름을 우선순위로 시도한다.
    """

    def pick(*keys, default=""):
        for k in keys:
            if k in row and row[k] not in (None, ""):
                return row[k]
        return default

    appraisal = int(pick("PBCT_APSL_ASES_AVG_AMT", "APSL_ASES_AVG_AMT", default=0) or 0)
    min_bid = int(pick("MIN_BID_PRC", "MINIMUM_BID_PRICE", default=0) or 0)

    return AuctionItem(
        source="onbid",
        item_id=str(pick("PBCT_NO", "CLTR_NO", "PLNM_NO")),
        title=str(pick("CLTR_NM", "USCBD_NM", default="(제목 없음)")),
        property_type=str(pick("GOODS_KIND_NM", "USCBD_NM", default="기타")),
        region_sido=str(pick("LDNM_ADRS_SIDO_NM", "ADDR_SIDO", default="")),
        region_sigungu=str(pick("LDNM_ADRS_SGG_NM", "ADDR_SGG", default="")),
        address=str(pick("LDNM_ADRS", "NMRD_ADRS", "ADDR", default="")),
        appraisal_price=appraisal,
        min_bid_price=min_bid,
        bid_start_date=pick("PBCT_BEGN_DTM", "BID_START_DT", default=None) or None,
        bid_end_date=pick("PBCT_CLS_DTM", "BID_END_DT", default=None) or None,
        source_url="https://www.onbid.co.kr",
        failed_count=int(pick("PBCT_CNT", default=0) or 0),
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
    """
    client = _get_client()
    raw_rows = client.read_data(_FUNC_GROUP, _FUNC_NAME)

    items = [_row_to_item(row) for row in raw_rows]

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
