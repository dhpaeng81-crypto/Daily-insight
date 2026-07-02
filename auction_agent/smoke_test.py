"""ONBID_SERVICE_KEY 연결 확인용 스모크 테스트.

서비스키 값은 출력하지 않는다.
"""

from auction_agent.onbid_source import _ENDPOINT, _request, search_onbid


def _raw_diagnostic() -> None:
    """기본 파라미터로 요청해 원본 응답의 총 건수만 확인한다."""
    print("=== RAW REQUEST DIAGNOSTIC ===")
    print(f"Endpoint: {_ENDPOINT}")
    try:
        payload = _request({"numOfRows": 1})
        body = payload.get("body", {})
        print(f"header: {payload.get('header')}")
        print(f"totalCount: {body.get('totalCount')}")
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
