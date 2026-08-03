"""텔레그램으로 실제 검색 결과 샘플을 보내보는 1회성 검증 스크립트.

기존 TELEGRAM_TOKEN/TELEGRAM_CHAT_ID 시크릿을 재사용한다 (Daily Briefing과 동일).
python-telegram-bot의 Application을 띄우지 않고 Bot API를 직접 호출한다.
"""

import os

import requests

from auction_agent.onbid_source import search_onbid
from auction_agent.telegram_bot import DISCLAIMER, _format_item


def main() -> None:
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    items = search_onbid()[:3]
    if not items:
        text = "[테스트] 부동산 경매 에이전트: 검색 결과가 없습니다."
    else:
        text = (
            "[테스트] 부동산 경매 에이전트 연동 확인\n\n"
            + "\n\n".join(_format_item(i) for i in items)
            + DISCLAIMER
        )

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    print("전송 결과:", resp.json().get("ok"))


if __name__ == "__main__":
    main()
