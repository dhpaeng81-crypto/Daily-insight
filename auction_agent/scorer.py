"""규칙 기반 필터링/스코어링.

LLM 호출 없이 가격 메리트 위주로 1차 정렬한다. 점수가 낮을수록(=낙찰가율이
낮고 유찰이 많을수록) 가격 메리트가 크다고 본다.
"""

from typing import List

from .models import AuctionItem, UserProfile


def score_item(item: AuctionItem) -> float:
    price_rate_score = item.bid_price_rate  # 낮을수록 좋음 (0~1대)
    failed_bonus = -0.05 * item.failed_count  # 유찰 1회당 가점
    return price_rate_score + failed_bonus


def filter_and_rank(items: List[AuctionItem], profile: UserProfile) -> List[AuctionItem]:
    filtered = items

    if profile.property_types:
        filtered = [
            i for i in filtered
            if any(pt in i.property_type for pt in profile.property_types)
        ]
    if profile.regions:
        filtered = [
            i for i in filtered
            if any(r in f"{i.region_sido} {i.region_sigungu}" for r in profile.regions)
        ]
    if profile.budget_max:
        filtered = [i for i in filtered if i.min_bid_price and i.min_bid_price <= profile.budget_max]

    return sorted(filtered, key=score_item)
