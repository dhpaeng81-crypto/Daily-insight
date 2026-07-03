"""온비드 차세대 부동산 물건목록 조회서비스 연동.

구버전 PublicDataReader 라이브러리(1.1.1.post2)는 이 "차세대" 세대 API를
지원하지 않는다 (meta_dict에 없음). 실제 신청/승인받은 서비스는
`한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스`이며, 실제 GitHub
Actions에서 라이브 호출로 검증한 End Point와 파라미터는 다음과 같다
(2026-07-02 확인):

    End Point: https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2

data.go.kr 활용신청 페이지의 요청 파라미터 표에는 모든 필드가 "예시값"처럼
나열되어 있어 어떤 게 필수인지 알 수 없었는데, 실제 호출로 확인한 결과 아래
"단일 선택 코드" 필드들과 입찰기간은 반드시 값을 채워 보내야 하고
(비우면 NO_MANDATORY_REQUEST_PARAMETERS_ERROR), 지역/용도소분류/가격·면적
범위/자유검색 필드는 아예 생략해도 무방하다 (전체 대상으로 검색됨):
필수 - prptDivCd, bidDivCd, pvctTrgtYn, dispsMthodCd(요청 시 이 이름이지만
응답에는 dspsMthodCd로 옴), cptnMthodCd, cptnMthodNm, alcYn, bidPrdYmdStart,
bidPrdYmdEnd.

응답 필드명은 요청 파라미터명과 다른 경우가 많다 (예: 입찰시작일시는 요청 시
`bidPrdYmdStart`지만 응답에는 `cltrBidBgngDt`로 온다). `_row_to_item`은 실제
응답에서 확인된 필드명을 기준으로 작성했다.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

import requests

from .config import ONBID_SERVICE_KEY
from .models import AuctionItem

_ENDPOINT = "https://apis.data.go.kr/B010003/OnbidRlstListSrvc2/getRlstCltrList2"

KST = timezone(timedelta(hours=9))

# 확인된 유효한 재산종류코드 조합. 0007:압류재산, 0005:기타일반재산.
# 그 외 코드(공유재산·물류센터 등)를 추가하려면 실제 호출로 유효성을 검증하고 넣자
# - 존재하지 않는 코드를 섞으면 요청 전체가 거부된다.
_DEFAULT_PRPT_DIV_CD = "0007,0005"


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
        # 아래 8개는 실측 결과 필수 파라미터. 기본값은 "입찰 진행중/예정 매각 물건,
        # 오늘부터 90일 이내, 일반경쟁, 수의계약 대상 아님, 지분공유 아님"으로 넓게 잡는다.
        "prptDivCd": _DEFAULT_PRPT_DIV_CD,
        "bidDivCd": "0001",
        "pvctTrgtYn": "N",
        "dispsMthodCd": "0001",
        "cptnMthodCd": "0001",
        "cptnMthodNm": "일반경쟁",
        "alcYn": "N",
        "bidPrdYmdStart": today.strftime("%Y%m%d"),
        "bidPrdYmdEnd": (today + timedelta(days=90)).strftime("%Y%m%d"),
    }
    query.update(params)
    resp = requests.get(_ENDPOINT, params=query, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _extract_rows(payload: dict) -> List[dict]:
    """data.go.kr JSON 응답 봉투({'header':..., 'body':{'items':{'item':[...]}}})에서
    물건 목록을 꺼낸다."""
    body = payload.get("body", {})
    items = body.get("items", [])

    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []

    return items


def _row_to_item(row: dict) -> AuctionItem:
    """온비드 차세대 물건목록 응답 1건을 공통 스키마로 변환 (실제 응답 필드명 기준)."""

    def to_int(v):
        if v in (None, ""):
            return 0
        try:
            return int(float(str(v).replace(",", "").strip()))
        except ValueError:
            return 0

    sido = str(row.get("lctnSdnm") or "")
    sigungu = str(row.get("lctnSggnm") or "")
    emd = str(row.get("lctnEmdNm") or "")
    address = " ".join(p for p in [sido, sigungu, emd] if p)

    property_type = str(
        row.get("cltrUsgSclsCtgrNm")
        or row.get("cltrUsgMclsCtgrNm")
        or row.get("cltrUsgLclsCtgrNm")
        or "기타"
    )

    return AuctionItem(
        source="onbid",
        item_id=str(row.get("cltrMngNo") or row.get("pbctCdtnNo") or ""),
        title=str(row.get("onbidCltrNm") or "(제목 없음)"),
        property_type=property_type,
        region_sido=sido,
        region_sigungu=sigungu,
        address=address or str(row.get("onbidCltrNm") or ""),
        appraisal_price=to_int(row.get("apslEvlAmt")),
        min_bid_price=to_int(row.get("lowstBidPrcIndctCont")),
        bid_start_date=row.get("cltrBidBgngDt") or None,
        bid_end_date=row.get("cltrBidEndDt") or None,
        source_url="https://www.onbid.co.kr",
        failed_count=to_int(row.get("usbdNft")),
        area_m2=row.get("bldSqms") or row.get("landSqms"),
        status=str(row.get("pbctStatNm") or "진행중"),
    )


def search_onbid(
    property_types: Optional[List[str]] = None,
    regions: Optional[List[str]] = None,
    budget_max: Optional[int] = None,
) -> List[AuctionItem]:
    """조건에 맞는 온비드 부동산 공매 물건을 조회한다.

    property_types: 예) ["아파트", "주택"] (클라이언트 사이드 필터)
    regions: 예) ["서울특별시 강남구"] (클라이언트 사이드 필터)
    budget_max: 최저입찰가 상한 (원). 서버가 이 값을 정확히 어떻게 필터링하는지는
        검증되지 않아 우선 클라이언트 사이드에서도 다시 거른다.
    """
    payload = _request({})
    rows = _extract_rows(payload)
    items = [_row_to_item(row) for row in rows]

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
