"""ONBID_SERVICE_KEY 연결 확인용 스모크 테스트.

실제 API 응답 구조가 onbid_source.py의 필드 매핑 가정과 맞는지 확인한다.
서비스키 값은 출력하지 않는다.
"""

from auction_agent.onbid_source import _ENDPOINT, _request, search_onbid


def _raw_diagnostic() -> None:
    """차세대 온비드 물건목록 API에 기본 파라미터로 요청해 원본 응답을 출력한다."""
    print("=== RAW REQUEST DIAGNOSTIC (default params) ===")
    print(f"Endpoint: {_ENDPOINT}")
    try:
        payload = _request({"numOfRows": 3})
        print(f"응답 (앞 3000자):\n{str(payload)[:3000]}")
    except Exception as e:
        print(f"요청 자체가 실패함: {e}")
    print("=== END DIAGNOSTIC ===\n")


def _full_sample_diagnostic() -> None:
    """data.go.kr 활용신청 페이지의 전체 샘플 파라미터를 그대로 재현해본다.

    사용자가 미리보기 패널에서 이 조합으로 NODATA_ERROR(정상 처리, 결과 없음)를
    받았으므로, 여기서도 같은 결과가 나오는지 확인해 재현성을 검증한다.
    """
    sample_params = {
        "prptDivCd": "0007,0005",
        "bidDivCd": "0001",
        "pvctTrgtYn": "N",
        "dispsMthodCd": "0001",
        "cltrUsgLclsCtgrid": "10000",
        "cltrUsgMclsCtgrid": "10400",
        "cltrUsgSclsCtgrid": "10402",
        "cltrUsgLclsCtgrNm": "부동산",
        "cltrUsgMclsCtgrNm": "산업용지기타특수용건물",
        "cltrUsgSclsCtgrNm": "창고시설",
        "lctnSdnm": "경기도",
        "lctnSggnm": "고양시 일산동구",
        "lctnEmdNm": "마두동",
        "lowstBidPrcStart": "700000000",
        "lowstBidPrcEnd": "900000000",
        "landSqmsStart": "84",
        "landSqmsEnd": "100",
        "bldSqmsStart": "24",
        "bldSqmsEnd": "50",
        "bidPrdYmdStart": "20250518",
        "bidPrdYmdEnd": "20250618",
        "cptnMthodCd": "0001",
        "cptnMthodNm": "일반경쟁",
        "alcYn": "N",
        "usbdNfStart": "0",
        "usbdNfEnd": "3",
        "apslEvlAmtStart": "500000000",
        "apslEvlAmtEnd": "1000000000",
        "onbidCltrNm": "서울특별시 송파구 석촌동",
        "orgNm": "한국자산관리공사",
        "mdfcnYmdStart": "20251201",
        "mdfcnYmdEnd": "20251231",
    }
    print("=== FULL SAMPLE PARAM DIAGNOSTIC ===")
    try:
        payload = _request(sample_params)
        print(f"응답: {payload}")
    except Exception as e:
        print(f"요청 자체가 실패함: {e}")
    print("=== END DIAGNOSTIC ===\n")


def _narrowing_diagnostic() -> None:
    """전체 샘플에서 지역/가격/면적 등 좁히는 필드를 하나씩 빼며 어떤 조합이
    'NO_MANDATORY_REQUEST_PARAMETERS_ERROR' 없이 통과하는지 확인한다."""
    from datetime import datetime, timedelta, timezone

    KST = timezone(timedelta(hours=9))
    today = datetime.now(KST)
    wide_range = {
        "bidPrdYmdStart": today.strftime("%Y%m%d"),
        "bidPrdYmdEnd": (today + timedelta(days=90)).strftime("%Y%m%d"),
    }

    candidates = {
        "prptDivCd만 (0007,0005) + 넓은 기간": {
            "prptDivCd": "0007,0005",
            **wide_range,
        },
        "prptDivCd + bidDivCd + dispsMthodCd + 넓은 기간": {
            "prptDivCd": "0007,0005",
            "bidDivCd": "0001",
            "dispsMthodCd": "0001",
            **wide_range,
        },
        "prptDivCd + cltrUsgLclsCtgrid/Nm + 넓은 기간": {
            "prptDivCd": "0007,0005",
            "cltrUsgLclsCtgrid": "10000",
            "cltrUsgLclsCtgrNm": "부동산",
            **wide_range,
        },
    }

    for label, params in candidates.items():
        print(f"=== NARROWING DIAGNOSTIC: {label} ===")
        try:
            payload = _request(params)
            print(f"응답: {payload}")
        except Exception as e:
            print(f"요청 자체가 실패함: {e}")
        print()

    # 가설: 필드를 아예 생략하면 안 되고, 빈 문자열이라도 키 자체는 보내야
    # "필수 파라미터 누락"으로 처리되지 않을 수 있다.
    blank_open_search = {
        "prptDivCd": "0007,0005",
        "bidDivCd": "0001",
        "pvctTrgtYn": "N",
        "dispsMthodCd": "0001",
        "cltrUsgLclsCtgrid": "",
        "cltrUsgMclsCtgrid": "",
        "cltrUsgSclsCtgrid": "",
        "cltrUsgLclsCtgrNm": "",
        "cltrUsgMclsCtgrNm": "",
        "cltrUsgSclsCtgrNm": "",
        "lctnSdnm": "",
        "lctnSggnm": "",
        "lctnEmdNm": "",
        "lowstBidPrcStart": "",
        "lowstBidPrcEnd": "",
        "landSqmsStart": "",
        "landSqmsEnd": "",
        "bldSqmsStart": "",
        "bldSqmsEnd": "",
        **wide_range,
        "cptnMthodCd": "0001",
        "cptnMthodNm": "일반경쟁",
        "alcYn": "N",
        "usbdNfStart": "",
        "usbdNfEnd": "",
        "apslEvlAmtStart": "",
        "apslEvlAmtEnd": "",
        "onbidCltrNm": "",
        "orgNm": "",
        "mdfcnYmdStart": "",
        "mdfcnYmdEnd": "",
    }
    print("=== NARROWING DIAGNOSTIC: 전체 키 유지 + 좁히는 값만 빈 문자열 ===")
    try:
        payload = _request(blank_open_search)
        print(f"응답: {payload}")
    except Exception as e:
        print(f"요청 자체가 실패함: {e}")
    print()

    # 빈 문자열이 UNKNOWN_ERROR를 유발했다면, 숫자형 범위 필드는 빈 문자열
    # 대신 아주 넓은 범위(0~매우 큰 값)를 주고 문자열 필드만 빈 값으로 둔다.
    wide_numeric_open_search = {
        **blank_open_search,
        "lowstBidPrcStart": "0",
        "lowstBidPrcEnd": "999999999999",
        "landSqmsStart": "0",
        "landSqmsEnd": "999999",
        "bldSqmsStart": "0",
        "bldSqmsEnd": "999999",
        "usbdNfStart": "0",
        "usbdNfEnd": "99",
        "apslEvlAmtStart": "0",
        "apslEvlAmtEnd": "999999999999",
        "mdfcnYmdStart": "19000101",
        "mdfcnYmdEnd": today.strftime("%Y%m%d"),
    }
    print("=== NARROWING DIAGNOSTIC: 문자열 필드만 공백 + 숫자/날짜 범위는 아주 넓게 ===")
    try:
        payload = _request(wide_numeric_open_search)
        print(f"응답: {payload}")
    except Exception as e:
        print(f"요청 자체가 실패함: {e}")
    print()


def main() -> None:
    _raw_diagnostic()
    _full_sample_diagnostic()
    _narrowing_diagnostic()

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
