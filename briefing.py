import feedparser
import requests
from openai import OpenAI
from datetime import datetime, timezone, timedelta
import re
import os
import json
import glob
import random
import base64

# 주식 모듈 import
try:
    from stock_picker import get_stock_picks
    STOCK_ENABLED = True
except ImportError:
    STOCK_ENABLED = False
    print("stock_picker 모듈 없음. 주식 섹션 비활성화.")

# =====================
# 설정값
# =====================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# =====================
# 한국시간 (KST = UTC+9)
# =====================
KST = timezone(timedelta(hours=9))

def now_kst():
    return datetime.now(KST)

# =====================
# 기본 이미지 풀
# =====================
DEFAULT_IMAGES = {
    "Finance": [
        "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&q=80",
        "https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?w=800&q=80",
        "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?w=800&q=80",
        "https://images.unsplash.com/photo-1579621970563-ebec7560ff3e?w=800&q=80",
        "https://images.unsplash.com/photo-1642543492481-44e81e3914a7?w=800&q=80",
    ],
    "AI/IT": [
        "https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=800&q=80",
        "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=800&q=80",
        "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?w=800&q=80",
        "https://images.unsplash.com/photo-1635070041078-e363dbe005cb?w=800&q=80",
        "https://images.unsplash.com/photo-1544197150-b99a580bb7a8?w=800&q=80",
    ],
    "Energy": [
        "https://images.unsplash.com/photo-1466611653911-95081537e5b7?w=800&q=80",
        "https://images.unsplash.com/photo-1509391366360-2e959784a276?w=800&q=80",
        "https://images.unsplash.com/photo-1534224039826-c7a0eda0e6b3?w=800&q=80",
        "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?w=800&q=80",
        "https://images.unsplash.com/photo-1473341304170-971dccb5ac1e?w=800&q=80",
    ]
}

unsplash_cache = {}

def get_unsplash_image(category, keyword=""):
    if not UNSPLASH_ACCESS_KEY:
        return get_default_image(category)
    cache_key = f"{category}_{keyword}"
    if cache_key in unsplash_cache:
        return unsplash_cache[cache_key]
    try:
        response = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": keyword if keyword else category, "orientation": "landscape", "content_filter": "high"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=10
        )
        if response.status_code == 200:
            image_url = response.json()["urls"]["regular"]
            unsplash_cache[cache_key] = image_url
            return image_url
        return get_default_image(category)
    except Exception as e:
        print(f"Unsplash error: {e}")
        return get_default_image(category)

def get_default_image(category):
    return random.choice(DEFAULT_IMAGES.get(category, DEFAULT_IMAGES["Finance"]))

def extract_image(entry):
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url", "")
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url", "")
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("url", "")
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.get("summary", ""))
    if img_match:
        return img_match.group(1)
    return ""

# =====================
# RSS 피드
# =====================
RSS_FEEDS = [
    ("Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Finance", "https://www.hankyung.com/feed/finance"),
    ("AI/IT", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("AI/IT", "https://www.google.com/alerts/feeds/05107057229753784254/3732380721941349610"),
    ("Energy", "https://feeds.reuters.com/reuters/businessNews"),
    ("Energy", "https://www.google.com/alerts/feeds/05107057229753784254/4810996089673190473")
]

def collect_news():
    all_news = []
    for category, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get("title", url)
            count = 0
            for entry in feed.entries:
                if count >= 5:
                    break
                title = entry.get("title", "").strip()
                if not title:
                    continue
                summary = re.sub('<[^>]+>', '', entry.get("summary", ""))[:200]
                link = entry.get("link", "")
                image = extract_image(entry)
                if not image:
                    image = get_unsplash_image(category, " ".join(title.split()[:3]))
                all_news.append({
                    "category": category,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "image": image,
                    "source": source_name
                })
                count += 1
            print(f"OK: {category} ({source_name}) - {count}개 수집")
        except Exception as e:
            print(f"Error ({url}): {e}")
    print(f"총 수집: {len(all_news)}개")
    return all_news

def translate_single(news_item):
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "한국어 번역가입니다. 반드시 한국어로만 답하세요."},
            {"role": "user", "content": f"아래 뉴스를 한국어로 번역하고 2-3문장으로 요약해주세요.\n\n제목: {news_item['title']}\n내용: {news_item['summary']}"}
        ],
        max_tokens=300
    )
    return {"title": news_item["title"], "body": response.choices[0].message.content}

def generate_content(news_list):
    client = OpenAI(api_key=OPENAI_API_KEY)
    news_text = ""
    for i, n in enumerate(news_list):
        news_text += f"[index:{i}][{n['category']}] {n['title']}\n{n['summary']}\n\n"

    prompt = f"""
당신은 15년 경력의 한국인 금융·IT 시장 전문 애널리스트이자 뉴스레터 에디터입니다.
아래 뉴스를 바탕으로 Daily Insight 웹진 콘텐츠를 작성해주세요.

[절대 규칙]
- 모든 출력은 반드시 한국어로만 작성
- 영어 단어 사용 금지 (고유명사 제외)
- 전문용어는 쉬운 한국어로 풀어서 설명
- news_summaries는 수집된 모든 뉴스 포함
- original_index는 [index:숫자] 값과 정확히 일치
- 반드시 아래 JSON 형식으로만 응답 (다른 텍스트 없이)

[인사이트 기준]
1. 시장 방향성: 상승/하락/보합 방향과 이유 명확히
2. 수치 근거: 구체적인 % 변화, 금액, 기간 포함
3. 산업 파급효과: 영향받는 산업군 명시
4. 관련 기업: 국내외 기업 최소 2개 이상 언급
5. 투자 시사점: 구체적 대응 방향
6. 리스크 요인: 반대 시나리오 포함

{{
  "hero_title": "오늘의 핵심 헤드라인 20자 이내",
  "hero_desc": "오늘 시장 핵심 흐름 한 줄 요약 50자 이내",
  "finance_overview": "금융 시장 전반 흐름 3-4문장",
  "finance_comment": "투자자 핵심 인사이트 3-4문장. 국내외 기업 2개 이상, 대응 방향, 리스크 포함",
  "tech_overview": "AI·IT 시장 전반 흐름 3-4문장",
  "tech_comment": "IT·투자 관점 인사이트 3-4문장. 국내외 기업 2개 이상, 주목 포인트와 리스크 포함",
  "energy_overview": "에너지 시장 전반 흐름 3-4문장",
  "energy_comment": "에너지·투자 인사이트 3-4문장. 국내외 기업 2개 이상, 대응 방향과 리스크 포함",
  "key_insight_1": "핵심 인사이트 1: 구체적 수치·기업·방향성 포함",
  "key_insight_2": "핵심 인사이트 2: 구체적 수치·기업·방향성 포함",
  "key_insight_3": "핵심 인사이트 3: 리스크 또는 주의사항 포함",
  "news_summaries": [
    {{
      "category": "Finance 또는 AI/IT 또는 Energy",
      "title": "뉴스 제목 한국어로",
      "body": "3문장: 사실 요약, 왜 중요한지, 관련 기업이나 파급효과",
      "original_index": 0
    }}
  ]
}}

뉴스 데이터:
{news_text}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 15년 경력의 한국인 금융·IT 시장 전문 애널리스트입니다. 모든 출력은 반드시 한국어로만 작성하세요."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=5000
    )
    text = response.choices[0].message.content
    text = re.sub(r'```json|```', '', text).strip()
    return json.loads(text)

def make_news_card(news_item, summary, category_class):
    return f'''
    <div class="news-card">
      <div class="news-thumb">
        <img src="{news_item['image']}" alt="{summary['title']}" loading="lazy"
             onerror="this.parentElement.innerHTML='<div class=news-thumb-empty></div>'">
      </div>
      <div class="news-content">
        <div class="news-source-row">
          <span class="news-source">
            <span class="news-category-dot {category_class}"></span>
            {news_item['source']}
          </span>
        </div>
        <div class="news-title">
          <a href="{news_item['link']}" target="_blank">{summary['title']}</a>
        </div>
        <div class="news-body">{summary['body']}</div>
        <a href="{news_item['link']}" class="read-more" target="_blank">원문 읽기 →</a>
      </div>
    </div>'''

# =====================
# 주식 카드 HTML 생성
# =====================
def make_stock_card(stock_info, analysis, card_type="surge"):
    if not stock_info or not analysis:
        return ""

    change_color = "#dc2626" if stock_info.get("change_rate", 0) >= 0 else "#2563eb"
    change_sign = "+" if stock_info.get("change_rate", 0) >= 0 else ""

    if card_type == "surge":
        badge = "📈 급등 특징주"
        badge_class = "surge"
        extra_info = f'''
        <div class="stock-stat">
          <span class="stat-label">거래대금</span>
          <span class="stat-value">{stock_info.get('trading_value', 0) / 100000000:.0f}억원</span>
        </div>
        <div class="stock-stat">
          <span class="stat-label">거래량</span>
          <span class="stat-value">{stock_info.get('volume', 0):,}주</span>
        </div>'''
    else:
        badge = "🌍 외국인 순매수 1위"
        badge_class = "foreign"
        extra_info = f'''
        <div class="stock-stat">
          <span class="stat-label">순매수금액</span>
          <span class="stat-value">{stock_info.get('net_buy_amount', 0) / 100000000:.0f}억원</span>
        </div>
        <div class="stock-stat">
          <span class="stat-label">거래대금</span>
          <span class="stat-value">{stock_info.get('trading_value', 0) / 100000000:.0f}억원</span>
        </div>'''

    return f'''
    <div class="stock-card">
      <div class="stock-card-header">
        <div class="stock-badge {badge_class}">{badge}</div>
        <div class="stock-name-row">
          <span class="stock-name">{stock_info.get('name', '')}</span>
          <span class="stock-ticker">{stock_info.get('ticker', '')}</span>
        </div>
        <div class="stock-price-row">
          <span class="stock-price">{stock_info.get('close', 0):,}원</span>
          <span class="stock-change" style="color:{change_color}">{change_sign}{stock_info.get('change_rate', 0)}%</span>
        </div>
        <div class="stock-stats">
          {extra_info}
        </div>
      </div>
      <div class="stock-card-body">
        <div class="stock-comment">💬 {analysis.get('short_comment', '')}</div>
        <div class="stock-analysis-section">
          <div class="analysis-label">🏢 기업 개요</div>
          <div class="analysis-text">{analysis.get('company_overview', '')}</div>
        </div>
        <div class="stock-analysis-section">
          <div class="analysis-label">📊 주가 움직임 원인</div>
          <div class="analysis-text">{analysis.get('move_reason', '')}</div>
        </div>
        <div class="stock-analysis-section">
          <div class="analysis-label">💡 투자 포인트</div>
          <div class="analysis-text">{analysis.get('investment_point', '')}</div>
        </div>
        <div class="stock-analysis-section risk">
          <div class="analysis-label">⚠️ 리스크 요인</div>
          <div class="analysis-text">{analysis.get('risk_factor', '')}</div>
        </div>
      </div>
    </div>'''

def get_share_buttons_html(title, url):
    eu = requests.utils.quote(url, safe='')
    et = requests.utils.quote(title, safe='')
    twitter_url = f"https://twitter.com/intent/tweet?text={et}&url={eu}"
    return f'''
<div class="share-section">
  <div class="share-label">이 브리핑 공유하기</div>
  <div class="share-buttons">
    <a class="share-btn twitter" href="{twitter_url}" target="_blank" rel="noopener">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
      </svg>
      X에 공유
    </a>
    <button class="share-btn copy" onclick="copyLink()">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
      </svg>
      <span id="copy-text">링크 복사</span>
    </button>
  </div>
</div>
<script>
function copyLink() {{
  const url = '{url}';
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(url).then(() => {{
      const btn = document.getElementById('copy-text');
      btn.textContent = '복사됨 ✓';
      btn.parentElement.style.background = '#0f766e';
      btn.parentElement.style.color = '#fff';
      btn.parentElement.style.borderColor = '#0f766e';
      setTimeout(() => {{ btn.textContent = '링크 복사'; btn.parentElement.style.background = ''; btn.parentElement.style.color = ''; btn.parentElement.style.borderColor = ''; }}, 2000);
    }});
  }} else {{
    const t = document.createElement('textarea');
    t.value = url; t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select(); document.execCommand('copy'); document.body.removeChild(t);
    const btn = document.getElementById('copy-text');
    btn.textContent = '복사됨 ✓';
    setTimeout(() => {{ btn.textContent = '링크 복사'; }}, 2000);
  }}
}}
</script>'''

def get_common_css():
    return '''
@import url('https://hangeul.pstatic.net/hangeul_static/css/nanum-square.css');
:root {
  --ink: #18181b; --ink-soft: #52525b; --ink-muted: #a1a1aa;
  --bg: #fafaf9; --bg-card: #ffffff; --bg-subtle: #f4f4f5;
  --accent: #0f766e; --accent-light: #ccfbf1;
  --finance: #0369a1; --finance-bg: #e0f2fe;
  --tech: #6d28d9; --tech-bg: #ede9fe;
  --energy: #b45309; --energy-bg: #fef3c7;
  --stock-surge: #dc2626; --stock-surge-bg: #fef2f2;
  --stock-foreign: #0369a1; --stock-foreign-bg: #e0f2fe;
  --border: #e4e4e7; --radius: 12px;
  --font: 'NanumSquare', 'Apple SD Gothic Neo', sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--ink); font-family: var(--font); font-weight: 400; line-height: 1.8; }
a { color: inherit; text-decoration: none; }
.site-header { border-bottom: 1px solid var(--border); background: var(--bg-card); position: sticky; top: 0; z-index: 100; }
.header-inner { max-width: 780px; margin: 0 auto; padding: 0 24px; height: 56px; display: flex; align-items: center; justify-content: space-between; }
.logo { font-family: var(--font); font-size: 18px; font-weight: 800; letter-spacing: -0.02em; }
.logo span { color: var(--accent); }
.header-nav { display: flex; gap: 4px; font-size: 13px; align-items: center; }
.header-nav a { padding: 6px 12px; border-radius: 6px; color: var(--ink-muted); font-weight: 700; transition: background 0.15s, color 0.15s; }
.header-nav a:hover { background: var(--bg-subtle); color: var(--ink); }
.header-nav .active { color: var(--accent); background: var(--accent-light); }
.header-nav .divider { width: 1px; height: 16px; background: var(--border); margin: 0 4px; }
.site-footer { border-top: 1px solid var(--border); padding: 32px 24px; text-align: center; }
.footer-inner { max-width: 780px; margin: 0 auto; }
.footer-logo { font-family: var(--font); font-size: 16px; font-weight: 800; margin-bottom: 8px; }
.footer-logo span { color: var(--accent); }
.footer-desc { font-size: 12px; color: var(--ink-muted); margin-bottom: 16px; }
.footer-links { display: flex; justify-content: center; gap: 20px; font-size: 12px; color: var(--ink-muted); }
.footer-links a:hover { color: var(--accent); }
@media (min-width: 1024px) {
  .header-inner { max-width: 1080px; padding: 0 48px; }
  .footer-inner { max-width: 1080px; }
}
@media (max-width: 600px) { .header-meta { display: none; } }
'''

def get_header_html(active="briefing"):
    d_class = "active" if active == "briefing" else ""
    a_class = "active" if active == "archive" else ""
    return f'''
<header class="site-header">
  <div class="header-inner">
    <div class="logo"><a href="index.html">Daily<span>Insight</span></a></div>
    <nav class="header-nav">
      <a href="index.html" class="{d_class}">금융·AI·에너지</a>
      <a href="archive.html" class="{a_class}">아카이브</a>
      <div class="divider"></div>
      <a href="politics_index.html">역사·정치</a>
    </nav>
  </div>
</header>'''

def get_footer_html():
    return '''
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-logo">Daily<span>Insight</span></div>
    <div class="footer-desc">매일 오전 7시, 투자자를 위한 핵심 인사이트</div>
    <div class="footer-links">
      <a href="index.html">금융·AI·에너지</a>
      <a href="archive.html">아카이브</a>
      <a href="politics_index.html">역사·정치 브리핑</a>
    </div>
  </div>
</footer>'''

def build_html(news_list, content, stock_data=None):
    today = now_kst().strftime("%Y년 %m월 %d일")
    today_num = now_kst().strftime("%Y%m%d")
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    page_url = f"{site_url}/index.html"

    finance_news = [n for n in news_list if n["category"] == "Finance"]
    tech_news = [n for n in news_list if n["category"] == "AI/IT"]
    energy_news = [n for n in news_list if n["category"] == "Energy"]

    summaries = content.get("news_summaries", [])
    summaries_by_index = {}
    for s in summaries:
        idx = s.get("original_index")
        if idx is not None:
            summaries_by_index[idx] = s
    summaries_by_title = {}
    for s in summaries:
        summaries_by_title[s.get("title", "").lower()] = s

    def get_summary(idx):
        if idx in summaries_by_index:
            return summaries_by_index[idx]
        orig_title = news_list[idx]["title"].lower()
        for title, s in summaries_by_title.items():
            words = title.split()[:3]
            if words and any(word in orig_title for word in words):
                return s
        return translate_single(news_list[idx])

    finance_cards = "".join([make_news_card(n, get_summary(news_list.index(n)), "finance") for n in finance_news[:3]])
    tech_cards = "".join([make_news_card(n, get_summary(news_list.index(n)), "tech") for n in tech_news[:3]])
    energy_cards = "".join([make_news_card(n, get_summary(news_list.index(n)), "energy") for n in energy_news[:3]])

    # 주식 섹션 HTML
    stock_section_html = ""
    if stock_data:
        surge_card = make_stock_card(
            stock_data.get("surge_stock"),
            stock_data.get("surge_analysis"),
            "surge"
        )
        foreign_card = make_stock_card(
            stock_data.get("foreign_stock"),
            stock_data.get("foreign_analysis"),
            "foreign"
        )
        if surge_card or foreign_card:
            date_str = stock_data.get("date", "")
            stock_date_display = ""
            if date_str:
                from datetime import datetime as dt2
                d = dt2.strptime(date_str, "%Y%m%d")
                wd = ["월","화","수","목","금","토","일"][d.weekday()]
                stock_date_display = f"{d.strftime('%Y년 %m월 %d일')} ({wd}요일)"
            stock_section_html = f'''
  <div class="section-divider"></div>
  <div class="section-header">
    <span class="section-pill stock">Stock</span>
    <span class="section-title">어제의 특징주</span>
    <span class="stock-date-badge">{stock_date_display}</span>
  </div>
  <p class="section-overview">전일 장 마감 기준으로 주요 특징주를 선정하고 AI가 심층 분석한 종목 보고서입니다. 투자 판단의 참고 자료로만 활용하시기 바랍니다.</p>
  <div class="stock-list">
    {surge_card}
    {foreign_card}
  </div>
  <div class="stock-disclaimer">
    ⚠️ 본 분석은 투자 권유가 아닙니다. 투자 결과에 대한 책임은 투자자 본인에게 있습니다.
  </div>'''

    hero_title = content.get("hero_title", "오늘의 Daily Insight")
    hero_desc = content.get("hero_desc", "")
    share_buttons = get_share_buttons_html(hero_title, page_url)
    common_css = get_common_css()

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Insight — {today}</title>
<meta property="og:title" content="Daily Insight — {today}">
<meta property="og:description" content="{hero_desc}">
<meta property="og:image" content="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&q=80">
<meta property="og:url" content="{page_url}">
<meta name="twitter:card" content="summary_large_image">
<style>
{common_css}
.hero {{ max-width: 780px; margin: 0 auto; padding: 56px 24px 40px; border-bottom: 1px solid var(--border); }}
.issue-badge {{ display: inline-flex; align-items: center; font-size: 11px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); background: var(--accent-light); padding: 4px 12px; border-radius: 100px; margin-bottom: 20px; }}
.hero-title {{ font-family: var(--font); font-size: clamp(24px, 5vw, 38px); font-weight: 800; line-height: 1.25; letter-spacing: -0.02em; margin-bottom: 16px; }}
.hero-desc {{ font-size: 16px; color: var(--ink-soft); max-width: 560px; margin-bottom: 24px; line-height: 1.7; }}
.hero-tags {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.tag {{ font-size: 12px; font-weight: 700; padding: 4px 12px; border-radius: 100px; border: 1px solid var(--border); color: var(--ink-soft); }}
.main {{ max-width: 780px; margin: 0 auto; padding: 48px 24px 80px; }}
.section-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1.5px solid var(--border); }}
.section-pill {{ font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; padding: 4px 10px; border-radius: 6px; }}
.section-pill.finance {{ background: var(--finance-bg); color: var(--finance); }}
.section-pill.tech {{ background: var(--tech-bg); color: var(--tech); }}
.section-pill.energy {{ background: var(--energy-bg); color: var(--energy); }}
.section-pill.stock {{ background: #fef2f2; color: #dc2626; }}
.stock-date-badge {{ font-size: 12px; color: var(--ink-muted); font-weight: 700; margin-left: auto; }}
.section-title {{ font-family: var(--font); font-size: 20px; font-weight: 800; }}
.section-overview {{ font-size: 15px; color: var(--ink-soft); line-height: 1.75; margin-bottom: 24px; padding: 16px 20px; background: var(--bg-subtle); border-left: 3px solid var(--border); border-radius: 0 8px 8px 0; }}
.news-list {{ display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }}
.news-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; display: flex; flex-direction: column; transition: box-shadow 0.2s; }}
.news-card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
.news-thumb {{ width: 100%; height: 200px; overflow: hidden; background: var(--bg-subtle); }}
.news-thumb img {{ width: 100%; height: 100%; object-fit: cover; object-position: center; display: block; transition: transform 0.3s; }}
.news-card:hover .news-thumb img {{ transform: scale(1.03); }}
.news-thumb-empty {{ width: 100%; height: 100%; background: var(--bg-subtle); }}
.news-content {{ padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; flex: 1; }}
.news-source-row {{ display: flex; align-items: center; }}
.news-source {{ font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-muted); }}
.news-category-dot {{ width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 5px; }}
.news-category-dot.finance {{ background: var(--finance); }}
.news-category-dot.tech {{ background: var(--tech); }}
.news-category-dot.energy {{ background: var(--energy); }}
.news-title {{ font-size: 15px; font-weight: 700; line-height: 1.45; color: var(--ink); }}
.news-title a:hover {{ color: var(--accent); }}
.news-body {{ font-size: 13px; color: var(--ink-soft); line-height: 1.7; }}
.read-more {{ font-size: 12px; font-weight: 700; color: var(--accent); margin-top: 4px; display: inline-flex; align-items: center; gap: 3px; }}
.analyst-note {{ background: var(--bg-card); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 0 10px 10px 0; padding: 20px 24px; margin-bottom: 48px; }}
.analyst-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); margin-bottom: 8px; }}
.analyst-text {{ font-size: 14px; color: var(--ink); line-height: 1.85; }}
.section-divider {{ height: 1px; background: var(--border); margin: 0 0 48px; }}
.summary-box {{ background: var(--ink); color: #fff; border-radius: var(--radius); padding: 32px 36px; margin-bottom: 48px; }}
.summary-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-light); margin-bottom: 20px; }}
.summary-title {{ font-family: var(--font); font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 20px; }}
.summary-list {{ list-style: none; display: flex; flex-direction: column; gap: 14px; }}
.summary-list li {{ display: grid; grid-template-columns: 28px 1fr; gap: 12px; font-size: 14px; color: #d4d4d8; line-height: 1.65; }}
.summary-num {{ font-family: var(--font); font-size: 20px; font-weight: 800; color: var(--accent-light); line-height: 1.2; opacity: 0.6; }}

/* 주식 특징주 카드 스타일 */
.stock-list {{ display: flex; flex-direction: column; gap: 20px; margin-bottom: 24px; }}
.stock-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }}
.stock-card-header {{ padding: 20px 24px; border-bottom: 1px solid var(--border); }}
.stock-badge {{ display: inline-flex; align-items: center; font-size: 11px; font-weight: 800; padding: 4px 12px; border-radius: 100px; margin-bottom: 12px; }}
.stock-badge.surge {{ background: #fef2f2; color: #dc2626; }}
.stock-badge.foreign {{ background: #e0f2fe; color: #0369a1; }}
.stock-name-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
.stock-name {{ font-family: var(--font); font-size: 20px; font-weight: 800; color: var(--ink); }}
.stock-ticker {{ font-size: 12px; color: var(--ink-muted); background: var(--bg-subtle); padding: 2px 8px; border-radius: 4px; font-weight: 700; }}
.stock-price-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
.stock-price {{ font-family: var(--font); font-size: 24px; font-weight: 800; color: var(--ink); }}
.stock-change {{ font-family: var(--font); font-size: 18px; font-weight: 800; }}
.stock-stats {{ display: flex; gap: 16px; flex-wrap: wrap; }}
.stock-stat {{ display: flex; flex-direction: column; gap: 2px; }}
.stat-label {{ font-size: 11px; color: var(--ink-muted); font-weight: 700; }}
.stat-value {{ font-size: 14px; font-weight: 800; color: var(--ink); }}
.stock-card-body {{ padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }}
.stock-comment {{ font-size: 14px; font-weight: 800; color: var(--accent); background: var(--accent-light); padding: 10px 16px; border-radius: 8px; }}
.stock-analysis-section {{ display: flex; flex-direction: column; gap: 6px; }}
.stock-analysis-section.risk {{ background: #fef2f2; padding: 12px 16px; border-radius: 8px; border-left: 3px solid #dc2626; }}
.analysis-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-muted); }}
.analysis-text {{ font-size: 14px; color: var(--ink); line-height: 1.8; }}
.stock-disclaimer {{ font-size: 12px; color: var(--ink-muted); text-align: center; padding: 12px; background: var(--bg-subtle); border-radius: 8px; margin-bottom: 48px; }}

.share-section {{ border-top: 1px solid var(--border); padding-top: 32px; margin-bottom: 48px; text-align: center; }}
.share-label {{ font-size: 12px; color: var(--ink-muted); letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; margin-bottom: 16px; }}
.share-buttons {{ display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }}
.share-btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 24px; border-radius: 100px; font-size: 13px; font-weight: 700; cursor: pointer; border: none; transition: transform 0.15s, box-shadow 0.15s; font-family: var(--font); text-decoration: none; }}
.share-btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
.share-btn.twitter {{ background: #000; color: #fff; }}
.share-btn.copy {{ background: var(--bg-subtle); color: var(--ink); border: 1px solid var(--border); transition: transform 0.15s, box-shadow 0.15s, background 0.2s, color 0.2s, border-color 0.2s; }}
@media (min-width: 1024px) {{
  .hero {{ max-width: 1080px; padding: 72px 48px 56px; }}
  .main {{ max-width: 1080px; padding: 56px 48px 100px; }}
  .hero-title {{ font-size: 48px; }}
  .hero-desc {{ font-size: 18px; max-width: 680px; }}
  .section-title {{ font-size: 24px; }}
  .section-overview {{ font-size: 16px; }}
  .news-list {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
  .news-thumb {{ height: 180px; }}
  .stock-list {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }}
  .analyst-text {{ font-size: 15px; }}
  .summary-box {{ padding: 40px 48px; }}
  .summary-title {{ font-size: 24px; }}
  .summary-list li {{ font-size: 15px; }}
}}
@media (min-width: 640px) and (max-width: 1023px) {{
  .news-list {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }}
  .news-thumb {{ height: 180px; }}
}}
@media (max-width: 639px) {{
  .hero {{ padding: 36px 20px 32px; }}
  .main {{ padding: 36px 20px 60px; }}
  .summary-box {{ padding: 24px 20px; }}
  .share-btn {{ padding: 9px 18px; font-size: 12px; }}
  .stock-price {{ font-size: 20px; }}
  .stock-change {{ font-size: 16px; }}
}}
</style>
</head>
<body>
{get_header_html("briefing")}

<section class="hero">
  <div class="issue-badge">오늘의 브리핑</div>
  <h1 class="hero-title">{hero_title}</h1>
  <p class="hero-desc">{hero_desc}</p>
  <div class="hero-tags">
    <span class="tag">💹 금융 시장</span>
    <span class="tag">🤖 AI · IT</span>
    <span class="tag">⚡ 에너지</span>
    <span class="tag">📈 특징주</span>
  </div>
</section>

<main class="main">
  <div class="section-header">
    <span class="section-pill finance">Finance</span>
    <span class="section-title">금융 시장</span>
  </div>
  <p class="section-overview">{content.get("finance_overview", "")}</p>
  <div class="news-list">{finance_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">💡 애널리스트 인사이트</div>
    <div class="analyst-text">{content.get("finance_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="section-header">
    <span class="section-pill tech">Tech</span>
    <span class="section-title">AI · IT 트렌드</span>
  </div>
  <p class="section-overview">{content.get("tech_overview", "")}</p>
  <div class="news-list">{tech_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">💡 애널리스트 인사이트</div>
    <div class="analyst-text">{content.get("tech_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="section-header">
    <span class="section-pill energy">Energy</span>
    <span class="section-title">에너지 · 산업</span>
  </div>
  <p class="section-overview">{content.get("energy_overview", "")}</p>
  <div class="news-list">{energy_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">💡 애널리스트 인사이트</div>
    <div class="analyst-text">{content.get("energy_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="summary-box">
    <div class="summary-label">오늘의 핵심 인사이트</div>
    <div class="summary-title">오늘 꼭 기억할 3가지</div>
    <ol class="summary-list">
      <li><span class="summary-num">1</span><span>{content.get("key_insight_1", "")}</span></li>
      <li><span class="summary-num">2</span><span>{content.get("key_insight_2", "")}</span></li>
      <li><span class="summary-num">3</span><span>{content.get("key_insight_3", "")}</span></li>
    </ol>
  </div>

  {stock_section_html}

  {share_buttons}
</main>

{get_footer_html()}
</body>
</html>'''

    filename = f"briefing_{today_num}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML saved: {filename}")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("index.html updated")
    return filename

def build_archive():
    files = sorted(glob.glob("briefing_*.html"), reverse=True)
    archive_items = ""
    for f in files:
        date_str = f.replace("briefing_", "").replace(".html", "")
        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            date_display = date_obj.strftime("%Y년 %m월 %d일")
            weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
            with open(f, "r", encoding="utf-8") as fp:
                html_content = fp.read()
            title_match = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_content, re.DOTALL)
            hero_title = title_match.group(1).strip() if title_match else "Daily Insight 브리핑"
            is_today = date_str == now_kst().strftime("%Y%m%d")
            today_badge = '<span class="today-badge">오늘</span>' if is_today else ''
            archive_items += f'''
      <a href="{f}" class="archive-card">
        <div class="archive-date">
          <span class="archive-date-num">{date_obj.strftime("%m.%d")}</span>
          <span class="archive-weekday">{weekday}요일</span>
        </div>
        <div class="archive-info">
          <div class="archive-title">{hero_title} {today_badge}</div>
          <div class="archive-meta">{date_display}</div>
        </div>
        <div class="archive-arrow">→</div>
      </a>'''
        except Exception as e:
            print(f"Archive item error ({f}): {e}")

    common_css = get_common_css()
    archive_html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Insight — 아카이브</title>
<style>
{common_css}
.archive-hero {{ max-width: 780px; margin: 0 auto; padding: 56px 24px 40px; border-bottom: 1px solid var(--border); }}
.archive-hero-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); background: var(--accent-light); display: inline-block; padding: 4px 12px; border-radius: 100px; margin-bottom: 20px; }}
.archive-hero-title {{ font-family: var(--font); font-size: clamp(24px, 5vw, 38px); font-weight: 800; line-height: 1.25; margin-bottom: 12px; }}
.archive-hero-desc {{ font-size: 15px; color: var(--ink-soft); }}
.archive-main {{ max-width: 780px; margin: 0 auto; padding: 40px 24px 80px; }}
.archive-count {{ font-size: 13px; color: var(--ink-muted); margin-bottom: 24px; font-weight: 700; }}
.archive-list {{ display: flex; flex-direction: column; gap: 12px; }}
.archive-card {{ display: grid; grid-template-columns: 64px 1fr auto; align-items: center; gap: 16px; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 20px; transition: box-shadow 0.2s, border-color 0.2s; cursor: pointer; }}
.archive-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,0.08); border-color: var(--accent); }}
.archive-date {{ display: flex; flex-direction: column; align-items: center; gap: 2px; }}
.archive-date-num {{ font-family: var(--font); font-size: 18px; font-weight: 800; color: var(--ink); line-height: 1; }}
.archive-weekday {{ font-size: 11px; color: var(--ink-muted); font-weight: 700; }}
.archive-info {{ display: flex; flex-direction: column; gap: 4px; }}
.archive-title {{ font-size: 14px; font-weight: 700; color: var(--ink); line-height: 1.4; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.archive-meta {{ font-size: 12px; color: var(--ink-muted); }}
.archive-arrow {{ font-size: 16px; color: var(--ink-muted); }}
.archive-card:hover .archive-arrow {{ color: var(--accent); }}
.today-badge {{ font-size: 10px; font-weight: 800; background: var(--accent); color: #fff; padding: 2px 8px; border-radius: 100px; }}
@media (min-width: 1024px) {{ .archive-hero {{ max-width: 1080px; padding: 72px 48px 56px; }} .archive-main {{ max-width: 1080px; padding: 40px 48px 100px; }} }}
@media (max-width: 600px) {{ .archive-hero {{ padding: 36px 20px 32px; }} .archive-main {{ padding: 32px 20px 60px; }} .archive-card {{ grid-template-columns: 52px 1fr auto; gap: 12px; padding: 14px 16px; }} }}
</style>
</head>
<body>
{get_header_html("archive")}
<section class="archive-hero">
  <div class="archive-hero-label">아카이브</div>
  <h1 class="archive-hero-title">지난 브리핑 모아보기</h1>
  <p class="archive-hero-desc">매일 오전 7시 발행된 Daily Insight 브리핑을 날짜별로 확인하세요.</p>
</section>
<main class="archive-main">
  <div class="archive-count">총 {len(files)}개의 브리핑</div>
  <div class="archive-list">{archive_items}</div>
</main>
{get_footer_html()}
</body>
</html>'''

    with open("archive.html", "w", encoding="utf-8") as f:
        f.write(archive_html)
    print("archive.html updated")

def push_to_github(files_to_push):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GitHub token or repo not set, skipping push")
        return

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    base_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents"

    for filepath in files_to_push:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            check = requests.get(f"{base_url}/{filepath}", headers=headers)
            sha = check.json().get("sha") if check.status_code == 200 else None
            payload = {
                "message": f"Update {filepath} - {now_kst().strftime('%Y%m%d %H:%M')}",
                "content": encoded
            }
            if sha:
                payload["sha"] = sha
            response = requests.put(f"{base_url}/{filepath}", headers=headers, json=payload)
            if response.status_code in [200, 201]:
                print(f"GitHub push OK: {filepath}")
            else:
                print(f"GitHub push failed: {filepath} - {response.status_code}")
        except Exception as e:
            print(f"GitHub push error ({filepath}): {e}")

def send_telegram(today, filename):
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    message = f"*Daily Insight* 발행 완료\n{today}\n\n👉 [오늘의 브리핑 보기]({site_url})"
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    )
    print("Telegram: OK")

if __name__ == "__main__":
    print("Step 1: Collecting news...")
    news_list = collect_news()

    print("Step 2: Generating content...")
    content = generate_content(news_list)
    print("Content generated")

    print("Step 3: Collecting stock picks...")
    stock_data = None
    if STOCK_ENABLED:
        try:
            stock_data = get_stock_picks()
            print("Stock picks collected")
        except Exception as e:
            print(f"Stock picks error: {e}")

    print("Step 4: Building HTML...")
    today = now_kst().strftime("%Y년 %m월 %d일")
    today_num = now_kst().strftime("%Y%m%d")
    filename = build_html(news_list, content, stock_data)

    print("Step 5: Building archive...")
    build_archive()

    print("Step 6: Pushing to GitHub...")
    push_to_github([
        "index.html",
        "archive.html",
        f"briefing_{today_num}.html"
    ])

    print("Step 7: Sending Telegram...")
    send_telegram(today, filename)

    print("All done!")
