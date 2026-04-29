from pykrx import stock
from openai import OpenAI
import pandas as pd
from datetime import datetime, timedelta
import os
import requests
import re

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# =====================
# 날짜 설정 — 전 영업일 기준 (오전 7시 실행 → 어제 데이터)
# =====================
def get_business_date():
    # 오전 7시 실행 기준 → 전 영업일 데이터 사용
    today = datetime.now()
    delta = 1
    while True:
        prev = today - timedelta(days=delta)
        if prev.weekday() < 5:  # 평일만
            return prev.strftime("%Y%m%d")
        delta += 1

def get_date_display(date_str):
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y년 %m월 %d일')} ({weekday}요일)"

def get_prev_business_date(date_str):
    date = datetime.strptime(date_str, "%Y%m%d")
    delta = 1
    while True:
        prev = date - timedelta(days=delta)
        if prev.weekday() < 5:  # 평일
            return prev.strftime("%Y%m%d")
        delta += 1

# =====================
# 특징주 1 — 주가 상승률 15% 이상 중 거래대금 최대
# =====================
def get_top_surge_stock(date_str):
    try:
        print(f"특징주 1 수집 중... (날짜: {date_str})")

        # 코스피 + 코스닥 전체 종목 OHLCV
        kospi = stock.get_market_ohlcv(date_str, market="KOSPI")
        kosdaq = stock.get_market_ohlcv(date_str, market="KOSDAQ")
        all_stocks = pd.concat([kospi, kosdaq])

        # 전일 종가
        prev_date = get_prev_business_date(date_str)
        kospi_prev = stock.get_market_ohlcv(prev_date, market="KOSPI")
        kosdaq_prev = stock.get_market_ohlcv(prev_date, market="KOSDAQ")
        all_prev = pd.concat([kospi_prev, kosdaq_prev])

        # 상승률 계산
        all_stocks = all_stocks[all_stocks["종가"] > 0]
        all_prev = all_prev[all_prev["종가"] > 0]

        merged = all_stocks.join(all_prev[["종가"]], rsuffix="_prev")
        merged = merged.dropna(subset=["종가_prev"])
        merged["상승률"] = (merged["종가"] - merged["종가_prev"]) / merged["종가_prev"] * 100

        # 15% 이상 상승 종목 필터
        surged = merged[merged["상승률"] >= 15].copy()

        if surged.empty:
            print("15% 이상 상승 종목 없음")
            return None

        # 거래대금 기준 정렬 (거래대금 = 거래금액)
        surged = surged.sort_values("거래대금", ascending=False)
        top = surged.iloc[0]
        ticker = surged.index[0]

        # 종목명 가져오기
        name = stock.get_market_ticker_name(ticker)

        result = {
            "ticker": ticker,
            "name": name,
            "close": int(top["종가"]),
            "change_rate": round(float(top["상승률"]), 2),
            "volume": int(top["거래량"]),
            "trading_value": int(top["거래대금"]),
            "open": int(top["시가"]),
            "high": int(top["고가"]),
            "low": int(top["저가"]),
        }
        print(f"특징주 1: {name} ({ticker}) +{result['change_rate']}%")
        return result

    except Exception as e:
        print(f"특징주 1 수집 오류: {e}")
        return None

# =====================
# 특징주 2 — 외국인 순매수 1위
# =====================
def get_top_foreign_buy_stock(date_str):
    try:
        print(f"특징주 2 수집 중... (날짜: {date_str})")

        # 코스피 외국인 순매수
        kospi_foreign = stock.get_market_net_purchases_of_equities(date_str, date_str, "KOSPI", "외국인")
        kosdaq_foreign = stock.get_market_net_purchases_of_equities(date_str, date_str, "KOSDAQ", "외국인")
        all_foreign = pd.concat([kospi_foreign, kosdaq_foreign])

        # 순매수금액 기준 정렬
        all_foreign = all_foreign.sort_values("순매수금액", ascending=False)

        if all_foreign.empty:
            print("외국인 순매수 데이터 없음")
            return None

        top = all_foreign.iloc[0]
        ticker = all_foreign.index[0]
        name = stock.get_market_ticker_name(ticker)

        # 당일 OHLCV
        ohlcv = stock.get_market_ohlcv(date_str, market="KOSPI")
        if ticker not in ohlcv.index:
            ohlcv = stock.get_market_ohlcv(date_str, market="KOSDAQ")

        prev_date = get_prev_business_date(date_str)
        prev_ohlcv_k = stock.get_market_ohlcv(prev_date, market="KOSPI")
        prev_ohlcv_q = stock.get_market_ohlcv(prev_date, market="KOSDAQ")
        prev_ohlcv = pd.concat([prev_ohlcv_k, prev_ohlcv_q])

        close = int(ohlcv.loc[ticker, "종가"]) if ticker in ohlcv.index else 0
        prev_close = int(prev_ohlcv.loc[ticker, "종가"]) if ticker in prev_ohlcv.index else 0
        change_rate = round((close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0

        result = {
            "ticker": ticker,
            "name": name,
            "close": close,
            "change_rate": change_rate,
            "net_buy_amount": int(top["순매수금액"]),
            "net_buy_volume": int(top["순매수수량"]) if "순매수수량" in top else 0,
            "volume": int(ohlcv.loc[ticker, "거래량"]) if ticker in ohlcv.index else 0,
            "trading_value": int(ohlcv.loc[ticker, "거래대금"]) if ticker in ohlcv.index else 0,
        }
        print(f"특징주 2: {name} ({ticker}) 외국인 순매수 {result['net_buy_amount']:,}원")
        return result

    except Exception as e:
        print(f"특징주 2 수집 오류: {e}")
        return None

# =====================
# 관련 뉴스 검색
# =====================
def get_stock_news(company_name):
    try:
        feed_url = f"https://news.google.com/rss/search?q={requests.utils.quote(company_name)}+주식&hl=ko&gl=KR&ceid=KR:ko"
        import feedparser
        feed = feedparser.parse(feed_url)
        news_list = []
        for entry in feed.entries[:5]:
            title = re.sub('<[^>]+>', '', entry.get("title", ""))
            news_list.append(title)
        return news_list
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        return []

# =====================
# AI 분석 보고서 생성
# =====================
def generate_stock_analysis(stock_info, stock_type="surge"):
    client = OpenAI(api_key=OPENAI_API_KEY)

    news = get_stock_news(stock_info["name"])
    news_text = "\n".join([f"- {n}" for n in news]) if news else "관련 뉴스 없음"

    if stock_type == "surge":
        context = f"""
종목명: {stock_info['name']} ({stock_info['ticker']})
당일 종가: {stock_info['close']:,}원
전일 대비 상승률: +{stock_info['change_rate']}%
거래량: {stock_info['volume']:,}주
거래대금: {stock_info['trading_value']:,}원
시가: {stock_info['open']:,}원 / 고가: {stock_info['high']:,}원 / 저가: {stock_info['low']:,}원
관련 최신 뉴스:
{news_text}
"""
        prompt_type = "주가 급등 종목"
        analysis_focus = "급등 원인, 지속 가능성, 단기 투자 시사점"
    else:
        context = f"""
종목명: {stock_info['name']} ({stock_info['ticker']})
당일 종가: {stock_info['close']:,}원
전일 대비 등락률: {'+' if stock_info['change_rate'] >= 0 else ''}{stock_info['change_rate']}%
외국인 순매수금액: {stock_info['net_buy_amount']:,}원
거래량: {stock_info['volume']:,}주
거래대금: {stock_info['trading_value']:,}원
관련 최신 뉴스:
{news_text}
"""
        prompt_type = "외국인 순매수 1위 종목"
        analysis_focus = "외국인 매수 배경, 기업 펀더멘털, 중기 투자 관점"

    prompt = f"""
당신은 15년 경력의 한국 주식시장 전문 애널리스트입니다.
아래 {prompt_type}에 대해 깊이 있는 분석 보고서를 작성해주세요.

[데이터]
{context}

[분석 기준]
- 모든 출력은 반드시 한국어로만 작성
- {analysis_focus} 중심으로 분석
- 구체적인 수치와 근거 포함
- 리스크 요인 반드시 포함
- 반드시 아래 JSON 형식으로만 응답 (다른 텍스트 없이)

{{
  "company_overview": "기업 개요 및 주요 사업 2-3문장",
  "move_reason": "주가 움직임 원인 분석 3-4문장 (구체적 근거 포함)",
  "investment_point": "투자 포인트 3-4문장 (수혜 요인, 성장 가능성)",
  "risk_factor": "주요 리스크 요인 2-3문장",
  "short_comment": "한 줄 핵심 코멘트 (20자 이내)"
}}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 한국 주식시장 전문 애널리스트입니다. 모든 분석은 반드시 한국어로 작성하세요."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=1500
    )
    import json
    text = response.choices[0].message.content
    text = re.sub(r'```json|```', '', text).strip()
    return json.loads(text)

# =====================
# 메인 실행 함수
# =====================
def get_stock_picks():
    date_str = get_business_date()
    print(f"주식 데이터 수집 날짜: {date_str}")

    result = {
        "date": date_str,
        "surge_stock": None,
        "foreign_stock": None,
        "surge_analysis": None,
        "foreign_analysis": None
    }

    # 특징주 1: 급등 + 거래대금 최대
    surge = get_top_surge_stock(date_str)
    if surge:
        result["surge_stock"] = surge
        print("특징주 1 AI 분석 중...")
        result["surge_analysis"] = generate_stock_analysis(surge, "surge")

    # 특징주 2: 외국인 순매수 1위
    foreign = get_top_foreign_buy_stock(date_str)
    if foreign:
        result["foreign_stock"] = foreign
        print("특징주 2 AI 분석 중...")
        result["foreign_analysis"] = generate_stock_analysis(foreign, "foreign")

    return result
