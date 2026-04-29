import FinanceDataReader as fdr
from openai import OpenAI
import pandas as pd
from datetime import datetime, timedelta, timezone
import os
import requests
import re
import time
import json

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 한국시간 (KST = UTC+9)
KST = timezone(timedelta(hours=9))
def now_kst():
    return datetime.now(KST)

# =====================
# 날짜 설정 — 전 영업일 기준
# =====================
def get_business_date():
    today = now_kst()
    delta = 1
    while True:
        prev = today - timedelta(days=delta)
        if prev.weekday() < 5:
            return prev.strftime("%Y%m%d")
        delta += 1

def get_date_display(date_str):
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y년 %m월 %d일')} ({weekday}요일)"

def fmt(date_str):
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

def prev_biz(date_str, n=1):
    d = datetime.strptime(date_str, "%Y%m%d")
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d.strftime("%Y%m%d")

# =====================
# FDR로 단일 종목 OHLCV 가져오기
# =====================
def get_ohlcv(ticker, start_str, end_str):
    try:
        df = fdr.DataReader(ticker, fmt(start_str), fmt(end_str))
        if df is not None and not df.empty:
            return df
    except Exception as e:
        pass
    return None

# =====================
# 특징주 1 — 전일 대비 상승률 15% 이상 중 거래대금 최대
# KRX 시총 상위 종목 중 스크리닝
# =====================
def get_top_surge_stock(date_str):
    try:
        print(f"특징주 1 수집 중... (날짜: {date_str})")
        pd_str = prev_biz(date_str, 1)
        ppd_str = prev_biz(date_str, 5)  # 5영업일 전부터 수집

        # 코스피 + 코스닥 분리 수집
        print("KOSPI/KOSDAQ 종목 리스트 수집 중...")

        def normalize_listing(df):
            col_map = {}
            for c in df.columns:
                cl = c.lower()
                if cl in ["code", "symbol", "종목코드"]:
                    col_map[c] = "Code"
                elif cl in ["name", "종목명"]:
                    col_map[c] = "Name"
                elif cl in ["marcap", "시가총액"]:
                    col_map[c] = "Marcap"
            return df.rename(columns=col_map)

        df_kospi = fdr.StockListing("KOSPI")
        df_kosdaq = fdr.StockListing("KOSDAQ")

        if (df_kospi is None or df_kospi.empty) and (df_kosdaq is None or df_kosdaq.empty):
            print("종목 리스트 수집 실패")
            return None

        frames = []
        if df_kospi is not None and not df_kospi.empty:
            df_kospi = normalize_listing(df_kospi)
            if "Code" in df_kospi.columns:
                if "Marcap" in df_kospi.columns:
                    df_kospi = df_kospi.sort_values("Marcap", ascending=False).head(150)
                else:
                    df_kospi = df_kospi.head(150)
                frames.append(df_kospi)
                print(f"KOSPI: {len(df_kospi)}개")

        if df_kosdaq is not None and not df_kosdaq.empty:
            df_kosdaq = normalize_listing(df_kosdaq)
            if "Code" in df_kosdaq.columns:
                if "Marcap" in df_kosdaq.columns:
                    df_kosdaq = df_kosdaq.sort_values("Marcap", ascending=False).head(150)
                else:
                    df_kosdaq = df_kosdaq.head(150)
                frames.append(df_kosdaq)
                print(f"KOSDAQ: {len(df_kosdaq)}개")

        if not frames:
            print("유효한 종목 리스트 없음")
            return None

        df_all = pd.concat(frames, ignore_index=True)

        name_map = {}
        if "Name" in df_all.columns and "Code" in df_all.columns:
            name_map = dict(zip(df_all["Code"], df_all["Name"]))

        tickers = df_all["Code"].dropna().tolist()
        print(f"스크리닝 대상: {len(tickers)}개 종목 (KOSPI+KOSDAQ)")

        surge_list = []
        threshold = 15.0

        for i, ticker in enumerate(tickers):
            try:
                df = get_ohlcv(ticker, ppd_str, date_str)
                if df is None or len(df) < 2:
                    continue

                # Close 컬럼 찾기
                close_col = next((c for c in df.columns if c.lower() in ["close", "종가"]), None)
                vol_col = next((c for c in df.columns if c.lower() in ["volume", "거래량"]), None)
                open_col = next((c for c in df.columns if c.lower() in ["open", "시가"]), None)
                high_col = next((c for c in df.columns if c.lower() in ["high", "고가"]), None)
                low_col = next((c for c in df.columns if c.lower() in ["low", "저가"]), None)
                change_col = next((c for c in df.columns if c.lower() in ["change", "등락률"]), None)

                if close_col is None:
                    continue

                today_row = df.iloc[-1]
                prev_row = df.iloc[-2]

                today_close = float(today_row[close_col])
                prev_close = float(prev_row[close_col])

                if prev_close <= 0 or today_close <= 0:
                    continue

                if change_col:
                    change_rate = float(today_row[change_col]) * 100
                else:
                    change_rate = (today_close - prev_close) / prev_close * 100

                volume = float(today_row[vol_col]) if vol_col else 0
                trading_value = today_close * volume

                if change_rate >= threshold:
                    surge_list.append({
                        "ticker": ticker,
                        "name": name_map.get(ticker, ticker),
                        "close": int(today_close),
                        "change_rate": round(change_rate, 2),
                        "volume": int(volume),
                        "trading_value": int(trading_value),
                        "open": int(today_row[open_col]) if open_col else 0,
                        "high": int(today_row[high_col]) if high_col else 0,
                        "low": int(today_row[low_col]) if low_col else 0,
                    })

                if (i + 1) % 50 == 0:
                    print(f"  진행: {i+1}/{len(tickers)}, 급등 후보: {len(surge_list)}개")

                time.sleep(0.03)

            except Exception:
                continue

        # 15% 이상 없으면 기준 완화
        if not surge_list:
            print("15% 이상 급등 종목 없음 — 상위 등락률 종목으로 대체")
            all_changes = []
            for ticker in tickers[:50]:
                try:
                    df = get_ohlcv(ticker, ppd_str, date_str)
                    if df is None or len(df) < 2:
                        continue
                    close_col = next((c for c in df.columns if c.lower() in ["close", "종가"]), None)
                    vol_col = next((c for c in df.columns if c.lower() in ["volume", "거래량"]), None)
                    if not close_col:
                        continue
                    today_close = float(df.iloc[-1][close_col])
                    prev_close = float(df.iloc[-2][close_col])
                    if prev_close <= 0:
                        continue
                    change_rate = (today_close - prev_close) / prev_close * 100
                    volume = float(df.iloc[-1][vol_col]) if vol_col else 0
                    all_changes.append({
                        "ticker": ticker,
                        "name": name_map.get(ticker, ticker),
                        "close": int(today_close),
                        "change_rate": round(change_rate, 2),
                        "volume": int(volume),
                        "trading_value": int(today_close * volume),
                        "open": 0, "high": 0, "low": 0,
                    })
                    time.sleep(0.03)
                except:
                    continue
            if all_changes:
                # 등락률 상위 1개
                surge_list = sorted(all_changes, key=lambda x: x["change_rate"], reverse=True)[:1]

        if not surge_list:
            print("급등 종목 없음")
            return None

        # 거래대금 기준 정렬
        surge_list.sort(key=lambda x: x["trading_value"], reverse=True)
        top = surge_list[0]
        print(f"특징주 1: {top['name']} ({top['ticker']}) +{top['change_rate']}%")
        return top

    except Exception as e:
        print(f"특징주 1 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# =====================
# 특징주 2 — 삼성전자 + 외국인 순매수 대형주 고정 분석
# (외국인 순매수 데이터 소스가 불안정하므로 안정적인 방식 사용)
# =====================
def get_top_foreign_buy_stock(date_str):
    try:
        print(f"특징주 2 수집 중... (날짜: {date_str})")
        ppd_str = prev_biz(date_str, 5)

        # 외국인 선호 대형주 후보 (코스피 대표 종목)
        # 이 중 최근 5일 외국인 순매수가 가장 많을 것으로 추정되는 종목을
        # 거래량 증가율로 대체 선정
        candidates = [
            # 코스피 대형주
            ("005930", "삼성전자"),
            ("000660", "SK하이닉스"),
            ("005380", "현대차"),
            ("035420", "NAVER"),
            ("051910", "LG화학"),
            ("006400", "삼성SDI"),
            ("105560", "KB금융"),
            ("055550", "신한지주"),
            ("012330", "현대모비스"),
            ("000270", "기아"),
            ("068270", "셀트리온"),
            ("207940", "삼성바이오로직스"),
            ("028260", "삼성물산"),
            ("066570", "LG전자"),
            ("003550", "LG"),
            ("034730", "SK"),
            ("017670", "SK텔레콤"),
            ("030200", "KT"),
            ("032830", "삼성생명"),
            ("086790", "하나금융지주"),
            ("316140", "우리금융지주"),
            ("024110", "기업은행"),
            ("018260", "삼성에스디에스"),
            ("009540", "HD한국조선해양"),
            ("011200", "HMM"),
            ("010950", "S-Oil"),
            ("096770", "SK이노베이션"),
            ("003670", "포스코퓨처엠"),
            ("005490", "POSCO홀딩스"),
            ("000810", "삼성화재"),
            ("011790", "SKC"),
            ("047050", "포스코인터내셔널"),
            ("003490", "대한항공"),
            ("010140", "삼성중공업"),
            ("042660", "한화오션"),
            ("064350", "현대로템"),
            ("012450", "한화에어로스페이스"),
            ("079550", "LIG넥스원"),
            ("034020", "두산에너빌리티"),
            ("267250", "HD현대중공업"),
            # 코스닥 대형주
            ("035720", "카카오"),
            ("247540", "에코프로비엠"),
            ("086520", "에코프로"),
            ("373220", "LG에너지솔루션"),
            ("196170", "알테오젠"),
            ("091990", "셀트리온헬스케어"),
            ("263750", "펄어비스"),
            ("293490", "카카오게임즈"),
            ("112040", "위메이드"),
            ("060310", "3S"),
        ]

        results = []
        for ticker, name in candidates:
            try:
                df = get_ohlcv(ticker, ppd_str, date_str)
                if df is None or len(df) < 2:
                    continue

                close_col = next((c for c in df.columns if c.lower() in ["close", "종가"]), None)
                vol_col = next((c for c in df.columns if c.lower() in ["volume", "거래량"]), None)

                if not close_col or not vol_col:
                    continue

                today_close = float(df.iloc[-1][close_col])
                prev_close = float(df.iloc[-2][close_col])
                today_vol = float(df.iloc[-1][vol_col])
                avg_vol = float(df[vol_col].mean())

                if prev_close <= 0 or avg_vol <= 0:
                    continue

                change_rate = (today_close - prev_close) / prev_close * 100
                vol_ratio = today_vol / avg_vol  # 거래량 비율 (외국인 활동 proxy)

                results.append({
                    "ticker": ticker,
                    "name": name,
                    "close": int(today_close),
                    "change_rate": round(change_rate, 2),
                    "net_buy_amount": 0,
                    "net_buy_volume": 0,
                    "volume": int(today_vol),
                    "trading_value": int(today_close * today_vol),
                    "vol_ratio": vol_ratio,
                })
                time.sleep(0.03)

            except Exception as e:
                print(f"  {name} 오류: {e}")
                continue

        if not results:
            print("대형주 데이터 수집 실패")
            return None

        # 거래량 급증 기준 정렬 (외국인 순매수 proxy)
        results.sort(key=lambda x: x["vol_ratio"], reverse=True)
        top = results[0]

        # vol_ratio 제거 (HTML 표시용 아님)
        top.pop("vol_ratio", None)

        print(f"특징주 2: {top['name']} ({top['ticker']}) 거래량 급증")
        return top

    except Exception as e:
        print(f"특징주 2 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# =====================
# 관련 뉴스
# =====================
def get_stock_news(company_name):
    try:
        import feedparser
        feed_url = f"https://news.google.com/rss/search?q={requests.utils.quote(company_name)}+주식&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(feed_url)
        return [re.sub('<[^>]+>', '', e.get("title", "")) for e in feed.entries[:5]]
    except:
        return []

# =====================
# AI 분석 보고서
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
거래량: {stock_info.get('volume', 0):,}주
거래대금 추정: {stock_info.get('trading_value', 0) / 100000000:.1f}억원
시가: {stock_info.get('open', 0):,}원 / 고가: {stock_info.get('high', 0):,}원 / 저가: {stock_info.get('low', 0):,}원
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
거래량: {stock_info.get('volume', 0):,}주
거래대금 추정: {stock_info.get('trading_value', 0) / 100000000:.1f}억원
관련 최신 뉴스:
{news_text}
"""
        prompt_type = "외국인 순매수 유력 종목 (거래량 급증 기준 선정)"
        analysis_focus = "외국인 매수 배경 추정, 기업 펀더멘털, 중기 투자 관점"

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
        print("특징주 1 선정 실패")

    time.sleep(2)

    # 특징주 2: 거래량 급증 대형주 (외국인 순매수 proxy)
    foreign = get_top_foreign_buy_stock(date_str)
    if foreign:
        result["foreign_stock"] = foreign
        print("특징주 2 AI 분석 중...")
        result["foreign_analysis"] = generate_stock_analysis(foreign, "foreign")
    else:
        print("특징주 2 선정 실패")

    return result
