import FinanceDataReader as fdr
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
        if prev.weekday() < 5:
            return prev.strftime("%Y%m%d")
        delta += 1

def get_date_display(date_str):
    date_obj = datetime.strptime(date_str, "%Y%m%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
    return f"{date_obj.strftime('%Y년 %m월 %d일')} ({weekday}요일)"

def date_to_str(date_str):
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

# =====================
# 특징주 1 — 전일 대비 상승률 15% 이상 중 거래대금 최대
# =====================
def get_top_surge_stock(date_str):
    try:
        print(f"특징주 1 수집 중... (날짜: {date_str})")
        date_fmt = date_to_str(date_str)

        # 전일 날짜
        prev_delta = 1
        while True:
            prev_date = datetime.strptime(date_str, "%Y%m%d") - timedelta(days=prev_delta)
            if prev_date.weekday() < 5:
                prev_date_str = prev_date.strftime("%Y%m%d")
                break
            prev_delta += 1
        prev_date_fmt = date_to_str(prev_date_str)

        # KRX 전체 종목 리스트
        print("종목 리스트 수집 중...")
        df_krx = fdr.StockListing('KRX')
        if df_krx is None or df_krx.empty:
            print("종목 리스트 수집 실패")
            return None

        print(f"전체 종목 수: {len(df_krx)}")

        # 상위 500개 종목만 샘플링 (시총 기준 정렬 후)
        # Code 컬럼 확인
        code_col = None
        for col in ["Code", "Symbol", "종목코드", "code"]:
            if col in df_krx.columns:
                code_col = col
                break

        name_col = None
        for col in ["Name", "종목명", "name"]:
            if col in df_krx.columns:
                name_col = col
                break

        if code_col is None:
            print(f"종목코드 컬럼 없음. 컬럼: {list(df_krx.columns)}")
            return None

        print(f"종목코드 컬럼: {code_col}, 종목명 컬럼: {name_col}")

        # 시총 컬럼으로 상위 300개 선택
        marcap_col = None
        for col in ["Marcap", "시가총액", "marcap"]:
            if col in df_krx.columns:
                marcap_col = col
                break

        if marcap_col:
            df_krx = df_krx.sort_values(marcap_col, ascending=False).head(300)
        else:
            df_krx = df_krx.head(300)

        tickers = df_krx[code_col].tolist()
        names = {row[code_col]: row[name_col] for _, row in df_krx.iterrows()} if name_col else {}

        surge_candidates = []
        print(f"종목별 데이터 수집 중... (총 {len(tickers)}개)")

        for i, ticker in enumerate(tickers):
            try:
                # 최근 2일 데이터 수집
                df = fdr.DataReader(ticker, prev_date_fmt, date_fmt)
                if df is None or len(df) < 2:
                    continue

                # 마지막 2개 행
                today_row = df.iloc[-1]
                prev_row = df.iloc[-2]

                today_close = float(today_row.get("Close", today_row.get("종가", 0)))
                prev_close = float(prev_row.get("Close", prev_row.get("종가", 0)))

                if prev_close <= 0 or today_close <= 0:
                    continue

                change_rate = (today_close - prev_close) / prev_close * 100

                # 거래대금
                volume = float(today_row.get("Volume", today_row.get("거래량", 0)))
                trading_value = today_close * volume  # 거래대금 추정

                # Change 컬럼 있으면 사용
                if "Change" in today_row.index:
                    change_rate = float(today_row["Change"]) * 100

                if change_rate >= 15:
                    surge_candidates.append({
                        "ticker": ticker,
                        "name": names.get(ticker, ticker),
                        "close": int(today_close),
                        "prev_close": int(prev_close),
                        "change_rate": round(change_rate, 2),
                        "volume": int(volume),
                        "trading_value": int(trading_value),
                        "open": int(today_row.get("Open", today_row.get("시가", 0))),
                        "high": int(today_row.get("High", today_row.get("고가", 0))),
                        "low": int(today_row.get("Low", today_row.get("저가", 0))),
                    })

                if (i + 1) % 50 == 0:
                    print(f"  진행: {i+1}/{len(tickers)} (급등 후보: {len(surge_candidates)}개)")

                time.sleep(0.05)  # 요청 간격

            except Exception as e:
                continue

        if not surge_candidates:
            print("15% 이상 급등 종목 없음 — 5% 이상으로 기준 완화")
            # 5% 이상으로 재시도
            for ticker in tickers[:100]:
                try:
                    df = fdr.DataReader(ticker, prev_date_fmt, date_fmt)
                    if df is None or len(df) < 2:
                        continue
                    today_row = df.iloc[-1]
                    prev_row = df.iloc[-2]
                    today_close = float(today_row.get("Close", 0))
                    prev_close = float(prev_row.get("Close", 0))
                    if prev_close <= 0:
                        continue
                    change_rate = (today_close - prev_close) / prev_close * 100
                    volume = float(today_row.get("Volume", 0))
                    if change_rate >= 5:
                        surge_candidates.append({
                            "ticker": ticker,
                            "name": names.get(ticker, ticker),
                            "close": int(today_close),
                            "change_rate": round(change_rate, 2),
                            "volume": int(volume),
                            "trading_value": int(today_close * volume),
                            "open": int(today_row.get("Open", 0)),
                            "high": int(today_row.get("High", 0)),
                            "low": int(today_row.get("Low", 0)),
                        })
                    time.sleep(0.05)
                except:
                    continue

        if not surge_candidates:
            print("급등 종목 없음")
            return None

        # 거래대금 기준 정렬
        surge_candidates.sort(key=lambda x: x["trading_value"], reverse=True)
        top = surge_candidates[0]
        print(f"특징주 1: {top['name']} ({top['ticker']}) +{top['change_rate']}%")
        return top

    except Exception as e:
        print(f"특징주 1 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return None

# =====================
# 특징주 2 — 네이버 금융 외국인 순매수 1위
# =====================
def get_top_foreign_buy_stock(date_str):
    try:
        print(f"특징주 2 수집 중... (외국인 순매수)")

        # 네이버 금융 외국인 순매수 상위 종목
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # 코스피 외국인 순매수
        url = "https://finance.naver.com/sise/sise_quant.naver?sosok=0"
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = "euc-kr"

        # 외국인 순매수 페이지
        url_foreign = "https://finance.naver.com/sise/sise_netbuy.naver?sosok=0"
        resp_f = requests.get(url_foreign, headers=headers, timeout=15)
        resp_f.encoding = "euc-kr"

        # 테이블 파싱
        tables = pd.read_html(resp_f.text, header=0)

        df = None
        for t in tables:
            if len(t.columns) >= 3 and len(t) > 5:
                df = t
                break

        if df is None:
            print("외국인 순매수 테이블 파싱 실패")
            return get_top_foreign_buy_fallback(date_str)

        print(f"외국인 테이블 컬럼: {list(df.columns)}")

        # 첫 번째 유효한 종목 찾기
        name_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
        df = df.dropna(subset=[name_col])
        df = df[df[name_col].astype(str).str.len() > 1]

        if df.empty:
            return get_top_foreign_buy_fallback(date_str)

        top_name = str(df.iloc[0][name_col]).strip()
        print(f"외국인 순매수 1위: {top_name}")

        # FDR로 해당 종목 코드 및 가격 검색
        df_krx = fdr.StockListing('KRX')
        code_col = next((c for c in ["Code", "Symbol"] if c in df_krx.columns), None)
        name_col_krx = next((c for c in ["Name", "종목명"] if c in df_krx.columns), None)

        if code_col and name_col_krx:
            match = df_krx[df_krx[name_col_krx].str.contains(top_name[:3], na=False)]
            if not match.empty:
                ticker = match.iloc[0][code_col]
                company_name = match.iloc[0][name_col_krx]

                date_fmt = date_to_str(date_str)
                prev_date = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=3)).strftime("%Y-%m-%d")
                df_price = fdr.DataReader(ticker, prev_date, date_fmt)

                if df_price is not None and len(df_price) >= 2:
                    today_row = df_price.iloc[-1]
                    prev_row = df_price.iloc[-2]
                    close = int(today_row.get("Close", 0))
                    prev_close = int(prev_row.get("Close", 0))
                    change_rate = round((close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
                    volume = int(today_row.get("Volume", 0))

                    result = {
                        "ticker": ticker,
                        "name": company_name,
                        "close": close,
                        "change_rate": change_rate,
                        "net_buy_amount": 0,
                        "net_buy_volume": 0,
                        "volume": volume,
                        "trading_value": close * volume,
                    }
                    print(f"특징주 2: {company_name} ({ticker})")
                    return result

        return get_top_foreign_buy_fallback(date_str)

    except Exception as e:
        print(f"특징주 2 수집 오류: {e}")
        import traceback
        traceback.print_exc()
        return get_top_foreign_buy_fallback(date_str)

def get_top_foreign_buy_fallback(date_str):
    """외국인 순매수 데이터 수집 실패 시 삼성전자로 대체"""
    try:
        print("삼성전자 데이터로 대체...")
        date_fmt = date_to_str(date_str)
        prev_date = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        df = fdr.DataReader("005930", prev_date, date_fmt)

        if df is not None and len(df) >= 2:
            today_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            close = int(today_row.get("Close", 0))
            prev_close = int(prev_row.get("Close", 0))
            change_rate = round((close - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0
            volume = int(today_row.get("Volume", 0))

            return {
                "ticker": "005930",
                "name": "삼성전자",
                "close": close,
                "change_rate": change_rate,
                "net_buy_amount": 0,
                "net_buy_volume": 0,
                "volume": volume,
                "trading_value": close * volume,
                "note": "외국인 순매수 데이터 수집 실패 — 삼성전자로 대체"
            }
    except Exception as e:
        print(f"대체 데이터 수집 오류: {e}")
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
거래대금 추정: {stock_info.get('trading_value', 0) / 100000000:.0f}억원
시가: {stock_info.get('open', 0):,}원 / 고가: {stock_info.get('high', 0):,}원 / 저가: {stock_info.get('low', 0):,}원
관련 최신 뉴스:
{news_text}
"""
        prompt_type = "주가 급등 종목"
        analysis_focus = "급등 원인, 지속 가능성, 단기 투자 시사점"
    else:
        net_buy = stock_info.get('net_buy_amount', 0)
        net_buy_str = f"{net_buy / 100000000:.0f}억원" if net_buy > 0 else "데이터 수집 중"
        context = f"""
종목명: {stock_info['name']} ({stock_info['ticker']})
전일 종가: {stock_info['close']:,}원
전일 대비 등락률: {'+' if stock_info['change_rate'] >= 0 else ''}{stock_info['change_rate']}%
외국인 순매수금액: {net_buy_str}
거래량: {stock_info.get('volume', 0):,}주
관련 최신 뉴스:
{news_text}
"""
        prompt_type = "외국인 순매수 상위 종목"
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
- 반드시 아래 JSON 형식으로만 응답

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

    # 특징주 2: 외국인 순매수 1위
    foreign = get_top_foreign_buy_stock(date_str)
    if foreign:
        result["foreign_stock"] = foreign
        print("특징주 2 AI 분석 중...")
        result["foreign_analysis"] = generate_stock_analysis(foreign, "foreign")
    else:
        print("특징주 2 선정 실패")

    return result
