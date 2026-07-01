"""텔레그램 봇 명령어 핸들러 (python-telegram-bot v20+, 폴링 실행용).

로컬에서 `python -m auction_agent.telegram_bot`으로 폴링 실행할 수 있다.
상시 운영 시에는 DESIGN.md 3.4절대로 웹훅 서버에 같은 핸들러들을 그대로
붙이면 된다.
"""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .config import TELEGRAM_TOKEN
from .models import UserProfile
from .onbid_source import search_onbid
from .court_auction_source import search_court_auction
from .profiles import delete_profile, get_profile, save_profile
from .scorer import filter_and_rank

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ASK_PROPERTY_TYPE, ASK_REGION, ASK_BUDGET, ASK_NOTIFY = range(4)

DISCLAIMER = (
    "\n\n※ 권리분석(선순위 임차인·근저당 등)은 자동 확인되지 않습니다. "
    "입찰 전 반드시 등기부등본을 직접 확인하세요."
)


def _search_all(property_types, regions, budget_max):
    items = search_onbid(property_types, regions, budget_max)
    items += search_court_auction(property_types, regions, budget_max)
    return items


def _format_item(item) -> str:
    return (
        f"[{item.source}] {item.title}\n"
        f"  {item.address} ({item.property_type})\n"
        f"  감정가 {item.appraisal_price:,}원 / 최저입찰가 {item.min_bid_price:,}원 "
        f"(낙찰가율 {item.bid_price_rate:.0%}, 유찰 {item.failed_count}회)\n"
        f"  {item.source_url}"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "부동산 경매/공매 추천 봇입니다.\n"
        "/검색 <유형> <지역> <예산> - 즉시 검색 (예: /검색 아파트 강남 500000000)\n"
        "/조건저장 - 관심 조건을 저장하고 정기 알림 받기\n"
        "/내조건 - 저장된 조건 확인\n"
        "/조건삭제 - 저장된 조건 삭제"
    )


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("사용법: /검색 <유형> <지역> <예산(원)>")
        return

    *region_and_type, budget_str = args
    property_type, *region_parts = region_and_type
    region = " ".join(region_parts)
    try:
        budget_max = int(budget_str)
    except ValueError:
        await update.message.reply_text("예산은 숫자(원 단위)로 입력해주세요.")
        return

    profile = UserProfile(
        chat_id=str(update.effective_chat.id),
        property_types=[property_type],
        regions=[region] if region else [],
        budget_max=budget_max,
    )
    items = _search_all(profile.property_types, profile.regions, profile.budget_max)
    ranked = filter_and_rank(items, profile)[:5]

    if not ranked:
        await update.message.reply_text("조건에 맞는 물건을 찾지 못했습니다." + DISCLAIMER)
        return

    reply = "\n\n".join(_format_item(i) for i in ranked)
    await update.message.reply_text(reply + DISCLAIMER)


async def save_profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("관심 물건 유형을 알려주세요 (예: 아파트, 상가)")
    return ASK_PROPERTY_TYPE


async def save_profile_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["property_types"] = [t.strip() for t in update.message.text.split(",")]
    await update.message.reply_text("관심 지역을 알려주세요 (예: 서울 강남구, 경기 성남시)")
    return ASK_REGION


async def save_profile_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["regions"] = [r.strip() for r in update.message.text.split(",")]
    await update.message.reply_text("예산 상한을 원 단위 숫자로 알려주세요 (예: 500000000)")
    return ASK_BUDGET


async def save_profile_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["budget_max"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("숫자로 다시 입력해주세요.")
        return ASK_BUDGET
    await update.message.reply_text("정기 알림을 받으시겠어요? (예/아니오)")
    return ASK_NOTIFY


async def save_profile_notify(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    notify_enabled = update.message.text.strip() in ("예", "네", "yes", "y")
    profile = UserProfile(
        chat_id=str(update.effective_chat.id),
        property_types=context.user_data["property_types"],
        regions=context.user_data["regions"],
        budget_max=context.user_data["budget_max"],
        notify_enabled=notify_enabled,
    )
    save_profile(profile)
    await update.message.reply_text("조건을 저장했습니다. /내조건 으로 확인할 수 있어요.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("조건 저장을 취소했습니다.")
    return ConversationHandler.END


async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = get_profile(str(update.effective_chat.id))
    if not profile:
        await update.message.reply_text("저장된 조건이 없습니다. /조건저장 으로 등록해보세요.")
        return
    await update.message.reply_text(
        f"유형: {', '.join(profile.property_types)}\n"
        f"지역: {', '.join(profile.regions)}\n"
        f"예산: {profile.budget_max:,}원\n"
        f"알림: {'켜짐' if profile.notify_enabled else '꺼짐'}"
    )


async def delete_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    delete_profile(str(update.effective_chat.id))
    await update.message.reply_text("저장된 조건을 삭제했습니다.")


def build_app() -> Application:
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN이 설정되어 있지 않습니다.")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("검색", search_command))
    app.add_handler(CommandHandler("내조건", my_profile))
    app.add_handler(CommandHandler("조건삭제", delete_profile_command))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("조건저장", save_profile_start)],
        states={
            ASK_PROPERTY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_type)],
            ASK_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_region)],
            ASK_BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_budget)],
            ASK_NOTIFY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_profile_notify)],
        },
        fallbacks=[CommandHandler("취소", cancel)],
    )
    app.add_handler(conv_handler)

    return app


if __name__ == "__main__":
    build_app().run_polling()
