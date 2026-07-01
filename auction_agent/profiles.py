"""사용자 프로필 저장/조회.

로컬 JSON 파일에 저장한다. 이 저장소는 공개 웹사이트로 퍼블리시되므로
저장 경로(auction_agent/data/)는 .gitignore 처리되어 있다. 실서비스에서는
AUCTION_PROFILES_PATH를 비공개 스토리지 경로로 바꿔서 사용하자.
"""

import json
import os
from dataclasses import asdict
from typing import Dict, Optional

from .config import AUCTION_PROFILES_PATH
from .models import UserProfile


def _load_all() -> Dict[str, dict]:
    if not os.path.exists(AUCTION_PROFILES_PATH):
        return {}
    with open(AUCTION_PROFILES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_all(data: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(AUCTION_PROFILES_PATH), exist_ok=True)
    with open(AUCTION_PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_profile(chat_id: str) -> Optional[UserProfile]:
    data = _load_all().get(str(chat_id))
    return UserProfile(**data) if data else None


def save_profile(profile: UserProfile) -> None:
    data = _load_all()
    data[str(profile.chat_id)] = asdict(profile)
    _save_all(data)


def delete_profile(chat_id: str) -> None:
    data = _load_all()
    data.pop(str(chat_id), None)
    _save_all(data)


def all_profiles() -> Dict[str, UserProfile]:
    return {cid: UserProfile(**p) for cid, p in _load_all().items()}
