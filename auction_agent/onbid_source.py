"""온비드 차세대 부동산 물건목록 조회서비스 연동.

구버전 PublicDataReader 라이브러리(1.1.1.post2)는 이 "차세대" 세대 API를
지원하지 않는다 (meta_dict에 없음). 실제 신청/승인받은 서비스는
`한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스`이며, 사용자가
공유한 data.go.kr 활용신청 상세 페이지 기준 End Point와 요청 파라미터는
다음과 같다 (2026-07-02 확인):

    End Point: https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2

응답(출력결과) 필드 명세는 아직 확보하지 못했다. `smoke_test.py`의 raw
diagnostic으로 실제 JSON 응답을 먼저 확인한 뒤 `_row_to_item`을 완성해야 한다.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from .config import ONBID_SERVICE_KEY
from .models import AuctionItem

_ENDPOINT = "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2"

KST = timezone(timedelta(hours=9))


def _request(params: dict) -> dict:
    if not ONBID_SERVICE_KEY:
        raise RuntimeError(
            "ONBID_SERVICE_KEY가 설정되어 있지 않습니다. "
            "auction_agent/README.md의 키 발급 안내를 참고하세요."
        )
    today = datetime.now(KST)
    query = {
        "serviceKey": requests.utils.unquote(ONBID_SERVICE_KEY),
        "resultType": "json",
        "pageNo": 1,
        "numOfRows": 10,
        # 입찰기간은 필수 파라미터로 보여, 기본값으로 "오늘 ~ 30일 후"를 준다.
        "bidPrdYmdStart": today.strftime("%Y%m%d"),
        "bidPrdYmdEnd": (today + timedelta(days=30)).strftime("%Y%m%d"),
    }
    query.update(params)
    resp = requests.get(_ENDPOINT, params=query, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _extract_rows(payload: dict) -> List[dict]:
    """data.go.kr JSON 응답 봉투에서 물건 목록(items)을 꺼낸다.

    정확한 응답 스키마를 아직 확보하지 못해 흔한 형태들을 방어적으로 시도한다.
    """
    body = payload.get("response", {}).get("body", payload.get("body", {}))
    items = body.get("items", body.get("item", []))

    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []

    return items


def _row_to_item(row: dict) -> AuctionItem:
    """온비드 차세대 물건목록 응답 1건을 공통 스키마로 변환.

    실제 응답 필드명이 확인되기 전까지는 요청 파라미터명과 동일한 규칙
    (cltrMngNo, onbidCltrNm, lctnSdnm 등)을 우선 시도하고, 모르는 필드는
    빈 값으로 둔다. 실제 응답을 보고 나서 이 함수를 다시 조정해야 한다.
    """

    def pick(*keys, default=""):
        for k in keys:
            if k in row and row[k] not in (None, ""):
                return row[k]
        return default

    def to_int(v):
        if v in (None, ""):
            return 0
        try:
            return int(str(v).replace(",", "").strip())
        except ValueError:
            return 0

    sido = str(pick("lctnSdnm", "lctnSdNm", default=""))
    sigungu = str(pick("lctnSggnm", "lctnSggNm", default=""))
    emd = str(pick("lctnEmdNm", default=""))
    address = " ".join(p for p in [sido, sigungu, emd] if p)

    return AuctionItem(
        source="onbid",
        item_id=str(pick("cltrMngNo", "pbctCdtnNo", "pbancMngNo", default="")),
        title=str(pick("onbidCltrNm", "cltrNm", default="(제목 없음)")),
        property_type=str(pick("cltrUsgSclsCtgrNm", "cltrUsgMclsCtgrNm", "cltrUsgLclsCtgrNm", default="기타")),
        region_sido=sido,
        region_sigungu=sigungu,
        address=address,
        appraisal_price=to_int(pick("apslEvlAmt", "apslEvlAmtStart")),
        min_bid_price=to_int(pick("lowstBidPrc", "lowstBidPrcStart")),
        bid_start_date=pick("bidPrdYmdStart", default=None) or None,
        bid_end_date=pick("bidPrdYmdEnd", default=None) or None,
        source_url="https://www.onbid.co.kr",
        failed_count=to_int(pick("usbdCnt", "usbdNfStart")),
    )


def search_onbid(
    property_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    budget_max: Optional[int] = None,
) -> List[AuctionItem]:
    """조건에 맞는 온비드 부동산 공매 물건을 조회한다.

    property_types: 예) ["아파트", "주택"] (클라이언트 사이드 필터)
    regions: 예) ["서울특별시 강남구"] (클라이언트 사이드 필터)
    budget_max: 최저입찰가 상한 (원) - 서버 사이드 필터(lowstBidPrcEnd)로 전달
    """
    params = {}
    if budget_max:
        params["lowstBidPrcEnd"] = budget_max

    payload = _request(params)
    rows = _extract_rows(payload)
    items = [_row_to_item(row) for row in rows]

    if property_types:
        items = [i for i in items if any(pt in i.property_type for pt in property_types)]
    if regions:
        items = [
            i for i in items
            if any(r in f"{i.region_sido} {i.region_sigungu}" for r in regions)
        ]

    return items
