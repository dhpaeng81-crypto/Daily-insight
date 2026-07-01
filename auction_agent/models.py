from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AuctionItem:
    """온비드 공매 / 법원경매 물건을 함께 다루기 위한 공통 스키마."""

    source: str  # "onbid" | "court"
    item_id: str
    title: str
    property_type: str  # 아파트/주택/상가/오피스텔/토지 등
    region_sido: str
    region_sigungu: str
    address: str
    appraisal_price: int  # 감정가 (원)
    min_bid_price: int  # 최저입찰가 (원)
    bid_start_date: Optional[str]
    bid_end_date: Optional[str]
    source_url: str
    failed_count: int = 0  # 유찰 횟수 (온비드는 회차로 대체 가능)
    area_m2: Optional[float] = None
    status: str = "진행중"
    rights_note: str = "권리분석은 등기부등본을 직접 확인하세요."

    @property
    def bid_price_rate(self) -> float:
        """최저입찰가 / 감정가. 낮을수록 가격 메리트가 크다."""
        if not self.appraisal_price:
            return 1.0
        return self.min_bid_price / self.appraisal_price


@dataclass
class UserProfile:
    """텔레그램 chat_id 기준 사용자별 관심 조건."""

    chat_id: str
    property_types: List[str] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    budget_max: Optional[int] = None
    notify_enabled: bool = False
    notify_freq: str = "daily"  # "daily" | "weekly" | "off"
