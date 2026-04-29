from pykrx import stock
from openai import OpenAI
import pandas as pd
from datetime import datetime, timedelta
import os
import requests
import re
import time
import json

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# =====================
# 날짜 설정 — 전 영업일 기준
# =====================
def get_business_date():
    today = datetime.now()
    delta = 1
    while True:
        prev = today - timedelta(days=delta)
        if prev.weekday() < 5:  # 평일만
            return prev.strftime("%Y%m%d")
        delta += 1

def get_prev_business_date(date_str):
    date = datetime.strptime(date_str, "%Y%m%d")
    delta = 1
    while True:
        prev = date - timedelta(days=delta)
        if prev.weekday() < 5:
            return prev.strftime("%Y%m%d")
        delta += 1

def get_date_display(date_str):
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y년 %m월 %d일')} ({weekday}요일)"

# =====================
# pykrx 안전 호출 (재시도 포함)
# =====================
def safe_krx_call(func, *args, retries=3, delay=5, **kwargs):
    for i in range(retries):
        try:
            result = func(*args, **kwargs)
            if result is not None and not result.empty:
                return result
            print(f"빈 데이터 반환 (시도 {i+1}/{retries})")
        except Exception as e:
            print(f"KRX 호출 오류 (시도 {i+1}/{retries}): {e}")
        if i < retries - 1:
            time.sleep(delay)
    return None

# =====================
# 특징주 1 — 전일 대비 상승률 15% 이상 중 거래대금 최대
# =====================
def get_top_surge_stock(date_str):
    try:
        print(f"특징주 1 수집 중... (날짜: {date_str})")
        prev_date = get_prev_business_date(date_str)

        # 전종목 OHLCV — 올바른 호출 방식 (날짜 1개)
        df_today = safe_krx_call(stock.get_market_ohlcv, date_str, market="KOSPI")
        df_today_q = safe_krx_call(stock.get_market_ohlcv, date_str, market="KOSDAQ")

        if df_today is None and df_today_q is None:
            print("코스피/코스닥 데이터 수집 실패")
            return None

        frames = []
        if df_today is not None:
            df_today["market"] = "KOSPI"
            frames.append(df_today)
        if df_today_q is not None:
            df_today_q["market"] = "KOSDAQ"
            frames.append(df_today_q)

        all_today = pd.concat(frames)

        # 전일 데이터
        df_prev = safe_krx_call(stock.get_market_ohlcv, prev_date, market="KOSPI")
        df_prev_q = safe_krx_call(stock.get_market_ohlcv, prev_date, market="KOSDAQ")

        frames_prev = []
        if df_prev is not None:
            frames_prev.append(df_prev)
        if df_prev_q is not None:
            frames_prev.append(df_prev_q)

        if not frames_prev:
            print("전일 데이터 수집 실패")
            return None

        all_prev = pd.concat(frames_prev)

        # 컬럼명 확인 및 상승률 계산
        print(f"컬럼명: {list(all_today.columns)}")

        # 종가 컬럼 찾기
        close_col = None
        for col in ["종가", "close", "Close"]:
            if col in all_today.columns:
                close_col = col
                break
        if close_col is None:
            print(f"종가 컬럼 없음. 컬럼: {list(all_today.columns)}")
            return None

        vol_col = None
        for col in ["거래대금", "거래금액", "volume_value"]:
            if col in all_today.columns:
                vol_col = col
                break

        # 상승률 계산
        today_close = all_today[close_col].copy()
        prev_close = all_prev[close_col].reindex(all_today.index)

        change_rate = ((today_close - prev_close) / prev_close * 100).round(2)

        all_today = all_today.copy()
        all_today["상승률"] = change_rate
        all_today = all_today.dropna(subset=["상승률"])

        # 15% 이상 상승 필터
        surged = all_today[all_today["상승률"] >= 15].copy()

        if surged.empty:
            print("15% 이상 상승 종목 없음 — 기준 완화하여 재시도 (5% 이상)")
            surged = all_today[all_today["상승률"] >= 5].copy()
            if surged.empty:
                return None

        # 거래대금 기준 정렬
        if vol_col and vol_col in surged.columns:
            surged = surged.sort_values(vol_col, ascending=False)
            trading_value = int(surged.iloc[0][vol_col])
        else:
            # 거래대금 없으면 거래량으로 대체
            vol_cols = [c for c in ["거래량", "volume"] if c in surged.columns]
            if vol_cols:
                surged = surged.sort_values(vol_cols[0], ascending=False)
            trading_value = 0

        ticker = surged.index[0]
        top = surged.iloc[0]

        # 종목명
        try:
            name = stock.get_market_ticker_name(ticker)
        except:
            name = ticker

        # 시가/고가/저가 컬럼 찾기
        open_col = next((c for c in ["시가", "open", "Open"] if c in top.index), None)
        high_col = next((c for c in ["고가", "high", "High"] if c in top.index), None)
        low_col = next((c for c in ["저가", "low", "Low"] if c in top.index), None)
        vol_count_col = next((c for c in ["거래량", "volume"] if c in top.index), None)

        result = {
            "ticker": ticker,
            "name": name,
            "close": int(top[close_col]),
            "change_rate": float(top["상승률"]),
            "volume": int(top[vol_count_col]) if vol_count_col else 0,
            "trading_value": trading_value,
            "open": int(top[open_col]) if open_col else 0,
            "high": int(top[high_col]) if high_col else 0,
            "low": int(top[low_col]) if low_col else 0,
        }
        print(f"특징주 1: {name} ({ticker}) +{result['change_rate']}%")
        return result

    except Exception as e:
        print(f"특징주 1 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# =====================
# 특징주 2 — 외국인 순매수 1위
# =====================
def get_top_foreign_buy_stock(date_str):
    try:
        print(f"특징주 2 수집 중... (날짜: {date_str})")
        prev_date = get_prev_business_date(date_str)

        # 외국인 순매수 데이터
        df_k = safe_krx_call(
            stock.get_market_net_purchases_of_equities,
            date_str, date_str, "KOSPI", "외국인"
        )
        df_q = safe_krx_call(
            stock.get_market_net_purchases_of_equities,
            date_str, date_str, "KOSDAQ", "외국인"
        )

        frames = []
        if df_k is not None:
            frames.append(df_k)
        if df_q is not None:
            frames.append(df_q)

        if not frames:
            print("외국인 순매수 데이터 수집 실패")
            return None

        all_foreign = pd.concat(frames)
        print(f"외국인 데이터 컬럼: {list(all_foreign.columns)}")

        # 순매수금액 컬럼 찾기
        net_col = None
        for col in ["순매수금액", "순매수대금", "net_buy_amount"]:
            if col in all_foreign.columns:
                net_col = col
                break

        if net_col is None:
            print(f"순매수금액 컬럼 없음. 컬럼: {list(all_foreign.columns)}")
            # 마지막 숫자형 컬럼 사용
            num_cols = all_foreign.select_dtypes(include='number').columns
            if len(num_cols) > 0:
                net_col = num_cols[-1]
                print(f"대체 컬럼 사용: {net_col}")
            else:
                return None

        all_foreign = all_foreign.sort_values(net_col, ascending=False)
        top = all_foreign.iloc[0]
        ticker = all_foreign.index[0]

        try:
            name = stock.get_market_ticker_name(ticker)
        except:
            name = ticker

        # 당일/전일 종가
        df_today_k = safe_krx_call(stock.get_market_ohlcv, date_str, market="KOSPI")
        df_today_q = safe_krx_call(stock.get_market_ohlcv, date_str, market="KOSDAQ")
        df_prev_k = safe_krx_call(stock.get_market_ohlcv, prev_date, market="KOSPI")
        df_prev_q = safe_krx_call(stock.get_market_ohlcv, prev_date, market="KOSDAQ")

        all_today = pd.concat([f for f in [df_today_k, df_today_q] if f is not None])
        all_prev = pd.concat([f for f in [df_prev_k, df_prev_q] if f is not None])

        close_col = next((c for c in ["종가", "close"] if c in all_today.columns), None)
        vol_col = next((c for c in ["거래대금", "거래금액"] if c in all_today.columns), None)
        vol_count_col = next((c for c in ["거래량", "volume"] if c in all_today.columns), None)

        close = int(all_today.loc[ticker, close_col]) if close_col and ticker in all_today.index else 0
        prev_close = int(all_prev.loc[ticker, close_col]) if close_col and ticker in all_prev.index else 0
        change_rate = round((close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
        trading_value = int(all_today.loc[ticker, vol_col]) if vol_col and ticker in all_today.index else 0
        volume = int(all_today.loc[ticker, vol_count_col]) if vol_count_col and ticker in all_today.index else 0

        # 순매수수량 컬럼 찾기
        net_vol_col = next((c for c in ["순매수수량", "net_buy_volume"] if c in top.index), None)

        result = {
            "ticker": ticker,
            "name": name,
            "close": close,
            "change_rate": change_rate,
            "net_buy_amount": int(top[net_col]),
            "net_buy_volume": int(top[net_vol_col]) if net_vol_col else 0,
            "volume": volume,
            "trading_value": trading_value,
        }
        print(f"특징주 2: {name} ({ticker}) 외국인 순매수 {result['net_buy_amount']:,}원")
        return result

    except Exception as e:
        print(f"특징주 2 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# =====================
# 관련 뉴스 검색
# =====================
def get_stock_news(company_name):
    try:
        import feedparser
        feed_url = f"https://news.google.com/rss/search?q={requests.utils.quote(company_name)}+주식&hl=ko&gl=KR&ceid=KR:ko"
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
전일 종가: {stock_info['close']:,}원
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
전일 종가: {stock_info['close']:,}원
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
  "short_comment": "한 줄 핵심 코멘트 20자 이내"
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
    text = response.choices[0].message.content
    text = re.sub(r'```json|```', '', text).strip()
    return json.loads(text)

# =====================
# 메인 실행 함수
# =====================
def get_stock_picks():
    date_str = get_business_date()
    print(f"주식 데이터 수집 날짜: {date_str} ({get_date_display(date_str)})")

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
    else:
        print("특징주 1 선정 실패 — 주식 섹션 부분 생략")

    time.sleep(2)  # KRX 서버 부하 방지

    # 특징주 2: 외국인 순매수 1위
    foreign = get_top_foreign_buy_stock(date_str)
    if foreign:
        result["foreign_stock"] = foreign
        print("특징주 2 AI 분석 중...")
        result["foreign_analysis"] = generate_stock_analysis(foreign, "foreign")
    else:
        print("특징주 2 선정 실패 — 주식 섹션 부분 생략")

    return result
