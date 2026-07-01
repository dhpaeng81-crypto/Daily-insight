"""ONBID_SERVICE_KEY 연결 확인용 스모크 테스트.

실제 API 응답 구조가 onbid_source.py의 필드 매핑 가정과 맞는지 확인한다.
서비스키 값은 출력하지 않는다.
"""

import requests

from auction_agent.config import ONBID_SERVICE_KEY
from auction_agent.onbid_source import search_onbid


def _raw_diagnostic() -> None:
    """PublicDataReader를 거치지 않고 원본 응답을 그대로 출력한다.

    get_data()가 파싱 실패(KeyError 등)를 조용히 삼키는 경우, 실제 온비드가
    보낸 에러 메시지(resultCode/resultMsg)를 확인하기 위한 용도.
    """
    url = "http://openapi.onbid.co.kr/openapi/services/ThingInfoInquireSvc/getUnifyUsageCltr"
    params = {
        "serviceKey": requests.utils.unquote(ONBID_SERVICE_KEY),
        "numOfRows": 5,
        "pageNo": 1,
    }
    print("=== RAW REQUEST DIAGNOSTIC ===")
    try:
        resp = requests.get(url, params=params, timeout=15, verify=False)
        print(f"HTTP status: {resp.status_code}")
        print(f"응답 본문 (앞 1500자):\n{resp.text[:1500]}")
    except Exception as e:
        print(f"요청 자체가 실패함: {e}")
    print("=== END DIAGNOSTIC ===\n")


def main() -> None:
    _raw_diagnostic()

    items = search_onbid()
    print(f"조회된 물건 수: {len(items)}")

    for item in items[:5]:
        print("-" * 40)
        print(f"제목: {item.title}")
        print(f"유형: {item.property_type}")
        print(f"주소: {item.address} (시도={item.region_sido}, 시군구={item.region_sigungu})")
        print(f"감정가: {item.appraisal_price:,} / 최저입찰가: {item.min_bid_price:,}")
        print(f"낙찰가율: {item.bid_price_rate:.0%} / 유찰횟수: {item.failed_count}")
        print(f"입찰기간: {item.bid_start_date} ~ {item.bid_end_date}")
        print(f"상태: {item.status}")

    if not items:
        print("응답이 비어 있습니다. ONBID_SERVICE_KEY 승인 상태 또는 API 파라미터를 확인하세요.")


if __name__ == "__main__":
    main()
