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

# =====================
# 뉴스 중복 제거 (제목 유사도 기반)
# =====================
def is_duplicate(title, existing_titles, threshold=0.7):
    words_new = set(re.findall(r"[가-힣a-zA-Z0-9]+", title.lower()))
    if len(words_new) == 0:
        return False
    for existing in existing_titles:
        words_exist = set(re.findall(r"[가-힣a-zA-Z0-9]+", existing.lower()))
        if len(words_exist) == 0:
            continue
        overlap = len(words_new & words_exist)
        similarity = overlap / max(len(words_new), len(words_exist))
        if similarity >= threshold:
            return True
    return False

def collect_news():
    all_news = []
    seen_titles = []

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
                if is_duplicate(title, seen_titles):
                    print(f"  중복 제거: {title[:30]}...")
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
                seen_titles.append(title)
                count += 1
            print(f"OK: {category} ({source_name}) - {count}개 수집")
        except Exception as e:
            print(f"Error ({url}): {e}")
    print(f"총 수집: {len(all_news)}개 (중복 제거 후)")
    return all_news

def translate_single(news_item):
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "한국어 번역가입니다. 반드시 한국어로만 답하세요."},
            {"role": "user", "content": f"아래 뉴스를 한국어로 번역하고 2-3문장으로 요약해주세요.\n\n제목: {news_item['title']}\n내용: {news_item['summary']}"}
        ],
        max_tokens=300
    )
    return {"title": news_item["title"], "body": response.choices[0].message.content}

def translate_single_en(news_item):
    """영문 뉴스 요약 — summary 매칭 실패 시 fallback"""
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "You are a financial news summarizer. Respond in English only."},
            {"role": "user", "content": f"Summarize the following news in 3-4 sentences in English. Include key facts, market impact, and what investors should watch.\n\nTitle: {news_item['title']}\nContent: {news_item['summary']}"}
        ],
        max_tokens=300
    )
    return {"title": news_item["title"], "body": response.choices[0].message.content}

# =====================
# 한국어 콘텐츠 생성
# =====================
def generate_content(news_list):
    client = OpenAI(api_key=OPENAI_API_KEY)
    news_text = ""
    for i, n in enumerate(news_list):
        news_text += f"[index:{i}][{n['category']}] {n['title']}\n{n['summary']}\n\n"

    prompt = f"""
당신은 20년 경력의 한국인 금융·IT·에너지 시장 전문 수석 애널리스트이자 투자 뉴스레터 에디터입니다.
아래 뉴스를 바탕으로 Daily Insight 웹진의 고품질 콘텐츠를 작성해주세요.
독자는 주식·채권·부동산 등 다양한 자산을 운용하는 한국인 개인투자자와 금융 전문가입니다.

[절대 규칙]
- 모든 출력은 반드시 한국어로만 작성
- 영어 단어 사용 금지 (회사명·지표명·고유명사 제외)
- 전문용어는 반드시 쉬운 한국어로 풀어서 설명
- news_summaries는 수집된 모든 뉴스 포함
- original_index는 [index:숫자] 값과 정확히 일치
- 반드시 아래 JSON 형식으로만 응답 (다른 텍스트 없이)

[인사이트 품질 기준 — 반드시 준수]
1. 방향성 명확화: 단순 사실 나열 금지. 상승/하락/보합/전환 방향과 이유를 한 문장으로 선언
2. 수치 필수 포함: % 변화, 금액(억원/조원), 기간(단기·중기·장기), 목표가 등 구체적 수치
3. 산업 연결고리: 해당 이슈가 상위산업·하위산업·공급망에 미치는 파급 경로를 명시
4. 기업 실명 언급: 국내 수혜기업 2개 이상 + 해외 관련기업 1개 이상 반드시 실명으로 언급
5. 투자 액션: "매수/매도/관망/비중확대/축소" 중 하나를 명시하고 그 근거 제시
6. 리스크 시나리오: 반대 시나리오(하락 원인, 정책 리스크, 지정학 리스크 등) 반드시 1개 이상 포함
7. 뉴스 해설: 단순 번역이 아닌 "왜 지금 이 뉴스가 중요한가" 맥락 설명 필수

{{
  "hero_title": "오늘의 핵심 헤드라인 20자 이내 (수치 또는 기업명 포함)",
  "hero_desc": "오늘 시장 전체를 관통하는 핵심 흐름 한 줄 요약 60자 이내 (방향성 + 핵심 키워드)",
  "finance_overview": "금융 시장 전반 흐름 4-5문장. 주요 지수 방향성과 등락폭, 섹터별 강약, 글로벌 매크로 환경 변화를 수치와 함께 구체적으로 서술",
  "finance_comment": "금융 투자 심층 인사이트 5-6문장. ①수혜 섹터와 구체적 이유 ②국내 수혜기업 2개 이상 실명+근거 ③해외 관련기업 1개 이상 ④단기/중기 투자 액션(매수·관망·축소 명시) ⑤반드시 포함해야 할 리스크 시나리오 1개",
  "tech_overview": "AI·IT 시장 전반 흐름 4-5문장. 기술 트렌드 변화, 주요 기업 동향, 시장 규모·성장률 수치, 국내 산업 영향 포함",
  "tech_comment": "AI·IT 투자 심층 인사이트 5-6문장. ①기술 변화로 수혜받는 국내 산업군 ②국내 수혜기업 2개 이상 실명+근거 ③해외 선도기업 1개 이상 ④투자 액션 명시 ⑤리스크 시나리오(기술 실패, 규제, 경쟁 심화 등) 1개",
  "energy_overview": "에너지 시장 전반 흐름 4-5문장. 유가·가스·전력 가격 방향성과 수치, 재생에너지 동향, 글로벌 수급 변화 포함",
  "energy_comment": "에너지·산업 투자 심층 인사이트 5-6문장. ①에너지 가격 변화의 산업 파급 경로 ②국내 수혜/피해기업 2개 이상 실명+근거 ③해외 관련기업 1개 이상 ④투자 액션 명시 ⑤리스크 시나리오(지정학, 수요 감소, 정책 변화 등) 1개",
  "key_insight_1": "핵심 인사이트 1 (40자 이내): 오늘 가장 중요한 투자 시그널",
  "key_insight_2": "핵심 인사이트 2 (40자 이내): 섹터 로테이션 또는 글로벌 자금흐름 관점의 핵심 메시지",
  "key_insight_3": "핵심 인사이트 3 (40자 이내): 반드시 리스크 또는 주의사항",
  "news_summaries": [
    {{
      "category": "Finance 또는 AI/IT 또는 Energy",
      "title": "뉴스 제목 한국어로 (구체적이고 명확하게)",
      "body": "4문장 해설: ①핵심 사실 요약(수치 포함) ②왜 지금 이 뉴스가 중요한지 맥락 ③국내 산업·기업에 미치는 영향 ④투자자가 주목해야 할 포인트",
      "original_index": 0
    }}
  ]
}}

뉴스 데이터:
{news_text}
"""
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {
                "role": "system",
                "content": """당신은 20년 경력의 한국인 금융·IT·에너지 시장 수석 애널리스트입니다.
모든 출력은 반드시 한국어로만 작성하세요.
인사이트는 반드시 구체적인 수치, 기업명, 투자 액션을 포함해야 합니다.
'전망이다', '주목된다' 같은 모호한 표현 대신 명확한 방향과 근거를 제시하세요.
독자가 이 브리핑만 읽어도 오늘 투자 결정을 내릴 수 있을 만큼 구체적으로 작성하세요."""
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=6000
    )
    text = response.choices[0].message.content
    text = re.sub(r'```json|```', '', text).strip()
    return json.loads(text)

# =====================
# 영문 콘텐츠 생성
# =====================
def generate_content_en(news_list, ko_content):
    client = OpenAI(api_key=OPENAI_API_KEY)
    news_text = ""
    for i, n in enumerate(news_list):
        news_text += f"[index:{i}][{n['category']}] {n['title']}\n{n['summary']}\n\n"

    ko_ref = f"""
Korean version reference (translate and adapt naturally into English):
- Hero title: {ko_content.get('hero_title', '')}
- Hero desc: {ko_content.get('hero_desc', '')}
- Finance overview: {ko_content.get('finance_overview', '')}
- Finance comment: {ko_content.get('finance_comment', '')}
- Tech overview: {ko_content.get('tech_overview', '')}
- Tech comment: {ko_content.get('tech_comment', '')}
- Energy overview: {ko_content.get('energy_overview', '')}
- Energy comment: {ko_content.get('energy_comment', '')}
- Key insight 1: {ko_content.get('key_insight_1', '')}
- Key insight 2: {ko_content.get('key_insight_2', '')}
- Key insight 3: {ko_content.get('key_insight_3', '')}
"""

    prompt = f"""
You are a senior financial analyst and investment newsletter editor with 20 years of experience in Korean and global markets.
Based on the Korean version reference and news data below, create the English version of Daily Insight briefing.
Adapt Korean market context for international readers (briefly explain Korean companies/indices when needed).

[Rules]
- Write everything in natural, professional English
- Keep the same analytical depth as the Korean version
- Include specific figures, company names, and investment actions
- Respond ONLY in JSON format (no other text)

{ko_ref}

{{
  "hero_title": "Today's headline under 15 words (include figures or company names)",
  "hero_desc": "One-line summary of today's key market theme under 20 words",
  "finance_overview": "4-5 sentences on financial market overview with specific index movements, sector performance, and macro environment",
  "finance_comment": "5-6 sentences of financial investment insights: ①benefiting sectors ②2+ Korean companies with rationale ③1+ global company ④investment action (buy/hold/reduce) ⑤risk scenario",
  "tech_overview": "4-5 sentences on AI/IT market trends with tech developments, key companies, growth figures, and impact on Korean industry",
  "tech_comment": "5-6 sentences of AI/IT investment insights: ①Korean industries benefiting ②2+ Korean companies ③1+ global leader ④investment action ⑤risk scenario",
  "energy_overview": "4-5 sentences on energy market trends with oil/gas/power price direction and global supply-demand",
  "energy_comment": "5-6 sentences of energy investment insights: ①industry impact chain ②2+ Korean companies ③1+ global company ④investment action ⑤risk scenario",
  "key_insight_1": "Key insight 1 (under 20 words): Most important investment signal today",
  "key_insight_2": "Key insight 2 (under 20 words): Sector rotation or global capital flow message",
  "key_insight_3": "Key insight 3 (under 20 words): Risk warning or caution point",
  "news_summaries": [
    {{
      "category": "Finance or AI/IT or Energy",
      "title": "News title in clear English",
      "body": "4 sentences: ①key facts with figures ②why this matters now ③impact on Korean industry/companies ④what investors should watch",
      "original_index": 0
    }}
  ]
}}

News data:
{news_text}
"""
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a senior financial analyst specializing in Korean and Asian markets. Write in professional, clear English. Include specific figures, company names, and actionable investment insights."
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=5000
    )
    text = response.choices[0].message.content
    text = re.sub(r'```json|```', '', text).strip()
    return json.loads(text)

# =====================
# 뉴스 카드 (한국어)
# =====================
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
# 뉴스 카드 (영문)
# =====================
def make_news_card_en(news_item, summary, category_class):
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
        <a href="{news_item['link']}" class="read-more" target="_blank">Read original →</a>
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

# =====================
# 공유 버튼
# =====================
def get_share_buttons_html(title, url, lang="ko"):
    eu = requests.utils.quote(url, safe='')
    et = requests.utils.quote(title, safe='')
    twitter_url = f"https://twitter.com/intent/tweet?text={et}&url={eu}"
    share_label = "이 브리핑 공유하기" if lang == "ko" else "Share This Briefing"
    share_x = "X에 공유" if lang == "ko" else "Share on X"
    copy_label = "링크 복사" if lang == "ko" else "Copy Link"
    copied_label = "복사됨 ✓" if lang == "ko" else "Copied ✓"
    fn_name = f"copyLink_{lang}"
    btn_id = f"copy-text-{lang}"
    return f'''
<div class="share-section">
  <div class="share-label">{share_label}</div>
  <div class="share-buttons">
    <a class="share-btn twitter" href="{twitter_url}" target="_blank" rel="noopener">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
      </svg>
      {share_x}
    </a>
    <button class="share-btn copy" onclick="{fn_name}()">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
      </svg>
      <span id="{btn_id}">{copy_label}</span>
    </button>
  </div>
</div>
<script>
function {fn_name}() {{
  const url = '{url}';
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(url).then(() => {{
      const btn = document.getElementById('{btn_id}');
      btn.textContent = '{copied_label}';
      btn.parentElement.style.background = '#0f766e';
      btn.parentElement.style.color = '#fff';
      btn.parentElement.style.borderColor = '#0f766e';
      setTimeout(() => {{ btn.textContent = '{copy_label}'; btn.parentElement.style.background = ''; btn.parentElement.style.color = ''; btn.parentElement.style.borderColor = ''; }}, 2000);
    }});
  }} else {{
    const t = document.createElement('textarea');
    t.value = url; t.style.position = 'fixed'; t.style.opacity = '0';
    document.body.appendChild(t); t.select(); document.execCommand('copy'); document.body.removeChild(t);
    const btn = document.getElementById('{btn_id}');
    btn.textContent = '{copied_label}';
    setTimeout(() => {{ btn.textContent = '{copy_label}'; }}, 2000);
  }}
}}
</script>'''

# =====================
# 공통 CSS
# =====================
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
.header-nav a { padding: 6px 10px; border-radius: 6px; color: var(--ink-muted); font-weight: 700; transition: background 0.15s, color 0.15s; white-space: nowrap; }
.header-nav a:hover { background: var(--bg-subtle); color: var(--ink); }
.header-nav .active { color: var(--accent); background: var(--accent-light); }
.header-nav .divider { width: 1px; height: 16px; background: var(--border); margin: 0 2px; flex-shrink: 0; }
.lang-btn { padding: 4px 8px !important; font-size: 11px !important; font-weight: 800 !important; border: 1.5px solid var(--border) !important; border-radius: 6px !important; color: var(--ink-soft) !important; flex-shrink: 0; }
.lang-btn:hover { border-color: var(--accent) !important; color: var(--accent) !important; background: var(--accent-light) !important; }
.lang-btn.active { border-color: var(--accent) !important; color: var(--accent) !important; background: var(--accent-light) !important; }
.hamburger { display: none; flex-direction: column; gap: 5px; cursor: pointer; padding: 6px; border: none; background: none; }
.hamburger span { width: 22px; height: 2px; background: var(--ink); border-radius: 2px; transition: all 0.3s; display: block; }
.mobile-menu { display: none; position: fixed; top: 56px; left: 0; right: 0; background: var(--bg-card); border-bottom: 1px solid var(--border); padding: 12px 20px; flex-direction: column; gap: 4px; z-index: 99; box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.mobile-menu a { padding: 10px 12px; border-radius: 8px; color: var(--ink-soft); font-weight: 700; font-size: 14px; display: block; }
.mobile-menu a:hover { background: var(--bg-subtle); color: var(--ink); }
.mobile-menu .active { color: var(--accent); background: var(--accent-light); }
.mobile-menu .lang-row { display: flex; gap: 8px; padding: 8px 12px; }
.mobile-menu .lang-row a { padding: 6px 16px; border: 1.5px solid var(--border); border-radius: 6px; font-size: 12px; font-weight: 800; }
.mobile-menu .lang-row .active { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
.mobile-menu.open { display: flex; }
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

# =====================
# 헤더/푸터 — KO/EN 버튼 포함
# =====================
def get_header_html(active="briefing", lang="ko"):
    d_class = "active" if active == "briefing" else ""
    a_class = "active" if active == "archive" else ""
    if lang == "ko":
        logo_href = "index.html"
        briefing_href = "index.html"
        archive_href = "archive.html"
        briefing_label = "금융·AI·에너지"
        archive_label = "아카이브"
        politics_label = "역사·정치"
        ko_class = "lang-btn active"
        en_class = "lang-btn"
    else:
        logo_href = "index_en.html"
        briefing_href = "index_en.html"
        archive_href = "archive_en.html"
        briefing_label = "Finance·AI·Energy"
        archive_label = "Archive"
        politics_label = "History·Politics"
        ko_class = "lang-btn"
        en_class = "lang-btn active"

    return f'''
<header class="site-header">
  <div class="header-inner">
    <div class="logo"><a href="{logo_href}">Daily<span>Insight</span></a></div>
    <nav class="header-nav desktop-nav">
      <a href="{briefing_href}" class="{d_class}">{briefing_label}</a>
      <a href="{archive_href}" class="{a_class}">{archive_label}</a>
      <div class="divider"></div>
      <a href="politics_index.html">{politics_label}</a>
      <div class="divider"></div>
      <a href="index.html" class="{ko_class}">KO</a>
      <a href="index_en.html" class="{en_class}">EN</a>
    </nav>
    <button class="hamburger" onclick="toggleMenu()" aria-label="메뉴">
      <span></span><span></span><span></span>
    </button>
  </div>
</header>
<nav class="mobile-menu" id="mobile-menu">
  <a href="{briefing_href}" class="{d_class}">{briefing_label}</a>
  <a href="{archive_href}" class="{a_class}">{archive_label}</a>
  <a href="politics_index.html">{politics_label}</a>
  <div class="lang-row">
    <a href="index.html" class="{ko_class}">한국어</a>
    <a href="index_en.html" class="{en_class}">English</a>
  </div>
</nav>
<script>
function toggleMenu() {{
  const menu = document.getElementById('mobile-menu');
  menu.classList.toggle('open');
  const spans = document.querySelectorAll('.hamburger span');
  if (menu.classList.contains('open')) {{
    spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
    spans[1].style.opacity = '0';
    spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
  }} else {{
    spans[0].style.transform = ''; spans[1].style.opacity = ''; spans[2].style.transform = '';
  }}
}}
document.addEventListener('click', function(e) {{
  const menu = document.getElementById('mobile-menu');
  const btn = document.querySelector('.hamburger');
  if (menu && btn && !menu.contains(e.target) && !btn.contains(e.target)) {{
    menu.classList.remove('open');
    const spans = document.querySelectorAll('.hamburger span');
    spans[0].style.transform = ''; spans[1].style.opacity = ''; spans[2].style.transform = '';
  }}
}});
</script>'''

def get_footer_html(lang="ko"):
    if lang == "ko":
        return '''
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-logo">Daily<span>Insight</span></div>
    <div class="footer-desc">매일 오전 7시, 투자자를 위한 핵심 인사이트</div>
    <div class="footer-links">
      <a href="index.html">금융·AI·에너지</a>
      <a href="archive.html">아카이브</a>
      <a href="politics_index.html">역사·정치 브리핑</a>
      <a href="index_en.html">English</a>
    </div>
  </div>
</footer>'''
    else:
        return '''
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-logo">Daily<span>Insight</span></div>
    <div class="footer-desc">Daily briefing for investors — Published every morning at 7AM KST</div>
    <div class="footer-links">
      <a href="index_en.html">Finance·AI·Energy</a>
      <a href="archive_en.html">Archive</a>
      <a href="politics_index.html">History·Politics</a>
      <a href="index.html">한국어</a>
    </div>
  </div>
</footer>'''

# =====================
# HTML 생성 (한국어 / 영문 공통)
# =====================
def build_html(news_list, content, stock_data=None, lang="ko"):
    today_ko = now_kst().strftime("%Y년 %m월 %d일")
    today_en = now_kst().strftime("%B %d, %Y")
    today_num = now_kst().strftime("%Y%m%d")
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"

    if lang == "ko":
        page_url = f"{site_url}/index.html"
        alt_url  = f"{site_url}/index_en.html"
        title    = f"Daily Insight — {today_ko}"
        html_lang = "ko"
    else:
        page_url = f"{site_url}/index_en.html"
        alt_url  = f"{site_url}/index.html"
        title    = f"Daily Insight — {today_en}"
        html_lang = "en"

    # 뉴스 분류
    finance_news = [n for n in news_list if n["category"] == "Finance"]
    tech_news    = [n for n in news_list if n["category"] == "AI/IT"]
    energy_news  = [n for n in news_list if n["category"] == "Energy"]

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
        for t, s in summaries_by_title.items():
            words = t.split()[:3]
            if words and any(w in orig_title for w in words):
                return s
        # 언어에 따라 올바른 번역 함수 사용
        if lang == "en":
            return translate_single_en(news_list[idx])
        return translate_single(news_list[idx])

    card_fn = make_news_card_en if lang == "en" else make_news_card
    finance_cards = "".join([card_fn(n, get_summary(news_list.index(n)), "finance") for n in finance_news[:2]])
    tech_cards    = "".join([card_fn(n, get_summary(news_list.index(n)), "tech")    for n in tech_news[:2]])
    energy_cards  = "".join([card_fn(n, get_summary(news_list.index(n)), "energy")  for n in energy_news[:2]])

    # 주식 섹션 (한국어 전용)
    stock_section_html = ""
    if stock_data and lang == "ko":
        surge_card   = make_stock_card(stock_data.get("surge_stock"),   stock_data.get("surge_analysis"),   "surge")
        foreign_card = make_stock_card(stock_data.get("foreign_stock"), stock_data.get("foreign_analysis"), "foreign")
        if surge_card or foreign_card:
            date_str = stock_data.get("date", "")
            stock_date_display = ""
            if date_str:
                from datetime import datetime as dt2
                d  = dt2.strptime(date_str, "%Y%m%d")
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

    hero_title = content.get("hero_title", "Daily Insight")
    hero_desc  = content.get("hero_desc", "")
    share_buttons = get_share_buttons_html(hero_title, page_url, lang)
    common_css = get_common_css()

    # 언어별 텍스트
    if lang == "ko":
        badge_text   = "오늘의 브리핑"
        tag1,tag2,tag3,tag4 = "💹 금융 시장","🤖 AI · IT","⚡ 에너지","📈 특징주"
        s_finance    = ("Finance","금융 시장")
        s_tech       = ("Tech","AI · IT 트렌드")
        s_energy     = ("Energy","에너지 · 산업")
        insight_lbl  = "💡 애널리스트 인사이트"
        summary_lbl  = "오늘의 핵심 인사이트"
        summary_ttl  = "오늘 꼭 기억할 3가지"
    else:
        badge_text   = "Today's Briefing"
        tag1,tag2,tag3,tag4 = "💹 Finance","🤖 AI · Tech","⚡ Energy","📈 Stocks"
        s_finance    = ("Finance","Financial Markets")
        s_tech       = ("Tech","AI · Tech Trends")
        s_energy     = ("Energy","Energy · Industry")
        insight_lbl  = "💡 Analyst Insights"
        summary_lbl  = "Today's Key Insights"
        summary_ttl  = "3 Things to Remember Today"

    html = f'''<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="UTF-8">
<meta name="google-site-verification" content="4z1YG668VEajfm1MyEU5V9KCZIb9AYbS5C3dQJ99FdM">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta property="og:title" content="{title}">
<meta property="og:description" content="{hero_desc}">
<meta property="og:image" content="https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800&q=80">
<meta property="og:url" content="{page_url}">
<meta name="twitter:card" content="summary_large_image">
<link rel="alternate" hreflang="{html_lang}" href="{page_url}">
<link rel="alternate" hreflang="{'en' if html_lang=='ko' else 'ko'}" href="{alt_url}">
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
  .news-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; max-width: 900px; }}
  .news-thumb {{ height: 180px; }}
  .stock-list {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }}
  .analyst-text {{ font-size: 15px; }}
  .summary-box {{ padding: 40px 48px; }}
  .summary-title {{ font-size: 24px; }}
  .summary-list li {{ font-size: 15px; }}
}}
@media (min-width: 640px) and (max-width: 1023px) {{
  .news-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
  .news-thumb {{ height: 180px; }}
}}
@media (max-width: 767px) {{
  .desktop-nav {{ display: none; }}
  .hamburger {{ display: flex; }}
}}
@media (min-width: 768px) {{
  .hamburger {{ display: none; }}
  .mobile-menu {{ display: none !important; }}
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
{get_header_html("briefing", lang)}

<section class="hero">
  <div class="issue-badge">{badge_text}</div>
  <h1 class="hero-title">{hero_title}</h1>
  <p class="hero-desc">{hero_desc}</p>
  <div class="hero-tags">
    <span class="tag">{tag1}</span>
    <span class="tag">{tag2}</span>
    <span class="tag">{tag3}</span>
    <span class="tag">{tag4}</span>
  </div>
</section>

<main class="main">
  <div class="section-header">
    <span class="section-pill finance">{s_finance[0]}</span>
    <span class="section-title">{s_finance[1]}</span>
  </div>
  <p class="section-overview">{content.get("finance_overview", "")}</p>
  <div class="news-list">{finance_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">{insight_lbl}</div>
    <div class="analyst-text">{content.get("finance_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="section-header">
    <span class="section-pill tech">{s_tech[0]}</span>
    <span class="section-title">{s_tech[1]}</span>
  </div>
  <p class="section-overview">{content.get("tech_overview", "")}</p>
  <div class="news-list">{tech_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">{insight_lbl}</div>
    <div class="analyst-text">{content.get("tech_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="section-header">
    <span class="section-pill energy">{s_energy[0]}</span>
    <span class="section-title">{s_energy[1]}</span>
  </div>
  <p class="section-overview">{content.get("energy_overview", "")}</p>
  <div class="news-list">{energy_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">{insight_lbl}</div>
    <div class="analyst-text">{content.get("energy_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="summary-box">
    <div class="summary-label">{summary_lbl}</div>
    <div class="summary-title">{summary_ttl}</div>
    <ol class="summary-list">
      <li><span class="summary-num">1</span><span>{content.get("key_insight_1", "")}</span></li>
      <li><span class="summary-num">2</span><span>{content.get("key_insight_2", "")}</span></li>
      <li><span class="summary-num">3</span><span>{content.get("key_insight_3", "")}</span></li>
    </ol>
  </div>

  {stock_section_html}
  {share_buttons}
</main>

{get_footer_html(lang)}
</body>
</html>'''

    # 파일 저장
    if lang == "ko":
        filename = f"briefing_{today_num}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        with open("index.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"KO saved: {filename}, index.html")
        return filename
    else:
        filename_en = f"briefing_en_{today_num}.html"
        with open(filename_en, "w", encoding="utf-8") as f:
            f.write(html)
        with open("index_en.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"EN saved: {filename_en}, index_en.html")
        return filename_en

# =====================
# 아카이브 생성 (한국어 / 영문)
# =====================
def build_archive(lang="ko"):
    if lang == "ko":
        files        = sorted(glob.glob("briefing_[0-9]*.html"), reverse=True)
        archive_file = "archive.html"
        archive_lbl  = "아카이브"
        archive_ttl  = "지난 브리핑 모아보기"
        archive_dsc  = "매일 오전 7시 발행된 Daily Insight 브리핑을 날짜별로 확인하세요."
        count_lbl    = f"총 {len(files)}개의 브리핑"
        today_lbl    = "오늘"
    else:
        files        = sorted(glob.glob("briefing_en_[0-9]*.html"), reverse=True)
        archive_file = "archive_en.html"
        archive_lbl  = "Archive"
        archive_ttl  = "Past Briefings"
        archive_dsc  = "Browse all Daily Insight briefings published every morning at 7AM KST."
        count_lbl    = f"{len(files)} briefings total"
        today_lbl    = "Today"

    archive_items = ""
    for f in files:
        prefix   = "briefing_en_" if lang == "en" else "briefing_"
        date_str = f.replace(prefix, "").replace(".html", "")
        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            if lang == "ko":
                date_display = date_obj.strftime("%Y년 %m월 %d일")
                wd_str = ["월","화","수","목","금","토","일"][date_obj.weekday()] + "요일"
            else:
                date_display = date_obj.strftime("%B %d, %Y")
                wd_str = date_obj.strftime("%a")
            with open(f, "r", encoding="utf-8") as fp:
                html_content = fp.read()
            title_match = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_content, re.DOTALL)
            hero_title  = title_match.group(1).strip() if title_match else "Daily Insight"
            is_today    = date_str == now_kst().strftime("%Y%m%d")
            today_badge = f'<span class="today-badge">{today_lbl}</span>' if is_today else ''
            archive_items += f'''
      <a href="{f}" class="archive-card">
        <div class="archive-date">
          <span class="archive-date-num">{date_obj.strftime("%m.%d")}</span>
          <span class="archive-weekday">{wd_str}</span>
        </div>
        <div class="archive-info">
          <div class="archive-title">{hero_title} {today_badge}</div>
          <div class="archive-meta">{date_display}</div>
        </div>
        <div class="archive-arrow">→</div>
      </a>'''
        except Exception as e:
            print(f"Archive item error ({f}): {e}")

    common_css   = get_common_css()
    html_lang_attr = "ko" if lang == "ko" else "en"
    archive_html = f'''<!DOCTYPE html>
<html lang="{html_lang_attr}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Insight — {archive_lbl}</title>
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
{get_header_html("archive", lang)}
<section class="archive-hero">
  <div class="archive-hero-label">{archive_lbl}</div>
  <h1 class="archive-hero-title">{archive_ttl}</h1>
  <p class="archive-hero-desc">{archive_dsc}</p>
</section>
<main class="archive-main">
  <div class="archive-count">{count_lbl}</div>
  <div class="archive-list">{archive_items}</div>
</main>
{get_footer_html(lang)}
</body>
</html>'''

    with open(archive_file, "w", encoding="utf-8") as f:
        f.write(archive_html)
    print(f"{archive_file} updated")

# =====================
# 사이트맵 생성 (영문 페이지 포함)
# =====================
def build_sitemap():
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    today    = now_kst().strftime("%Y-%m-%d")

    briefing_files    = sorted(glob.glob("briefing_[0-9]*.html"), reverse=True)
    briefing_en_files = sorted(glob.glob("briefing_en_[0-9]*.html"), reverse=True)
    politics_files    = sorted(glob.glob("politics_[0-9]*.html"), reverse=True)

    urls = []
    for loc, freq, pri in [
        (f"{site_url}/index.html",           "daily", "1.0"),
        (f"{site_url}/index_en.html",         "daily", "1.0"),
        (f"{site_url}/archive.html",          "daily", "0.8"),
        (f"{site_url}/archive_en.html",       "daily", "0.8"),
        (f"{site_url}/politics_index.html",   "daily", "0.9"),
        (f"{site_url}/politics_archive.html", "daily", "0.7"),
    ]:
        urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{pri}</priority>
  </url>""")

    for files, prefix in [
        (briefing_files,    "briefing_"),
        (briefing_en_files, "briefing_en_"),
        (politics_files,    "politics_"),
    ]:
        for i, f in enumerate(files):
            date_str = f.replace(prefix, "").replace(".html", "")
            try:
                date_obj = datetime.strptime(date_str, "%Y%m%d")
                lastmod  = date_obj.strftime("%Y-%m-%d")
                priority = "0.9" if i == 0 else "0.6"
                urls.append(f"""  <url>
    <loc>{site_url}/{f}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>never</changefreq>
    <priority>{priority}</priority>
  </url>""")
            except:
                continue

    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)
    print(f"sitemap.xml 생성 완료 ({len(urls)}개 URL)")

    robots = f"""User-agent: *
Allow: /

Sitemap: {site_url}/sitemap.xml
"""
    with open("robots.txt", "w", encoding="utf-8") as f:
        f.write(robots)
    print("robots.txt 생성 완료")

# =====================
# GitHub 업로드
# =====================
def push_to_github(files_to_push):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GitHub token or repo not set, skipping push")
        return
    headers  = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    base_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
    for filepath in files_to_push:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            check   = requests.get(f"{base_url}/{filepath}", headers=headers)
            sha     = check.json().get("sha") if check.status_code == 200 else None
            payload = {"message": f"Update {filepath} - {now_kst().strftime('%Y%m%d %H:%M')}", "content": encoded}
            if sha:
                payload["sha"] = sha
            resp = requests.put(f"{base_url}/{filepath}", headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                print(f"GitHub push OK: {filepath}")
            else:
                print(f"GitHub push failed: {filepath} - {resp.status_code}")
        except Exception as e:
            print(f"GitHub push error ({filepath}): {e}")

# =====================
# 텔레그램 발송
# =====================
def send_telegram(today, filename):
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    message  = f"*Daily Insight* 발행 완료\n{today}\n\n👉 [한국어 브리핑]({site_url})\n🇺🇸 [English Version]({site_url}/index_en.html)"
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    )
    print("Telegram: OK")

# =====================
# 실행
# =====================
if __name__ == "__main__":
    print("Step 1: Collecting news...")
    news_list = collect_news()

    print("Step 2: Generating KO content...")
    content_ko = generate_content(news_list)
    print("KO content generated")

    print("Step 3: Generating EN content...")
    try:
        content_en = generate_content_en(news_list, content_ko)
        print("EN content generated")
    except Exception as e:
        print(f"EN content generation failed: {e}")
        # 한국어 콘텐츠 기반으로 기본 영문 콘텐츠 생성
        content_en = {
            "hero_title": content_ko.get("hero_title", "Daily Insight"),
            "hero_desc": content_ko.get("hero_desc", "Today's market briefing"),
            "finance_overview": content_ko.get("finance_overview", ""),
            "finance_comment": content_ko.get("finance_comment", ""),
            "tech_overview": content_ko.get("tech_overview", ""),
            "tech_comment": content_ko.get("tech_comment", ""),
            "energy_overview": content_ko.get("energy_overview", ""),
            "energy_comment": content_ko.get("energy_comment", ""),
            "key_insight_1": content_ko.get("key_insight_1", ""),
            "key_insight_2": content_ko.get("key_insight_2", ""),
            "key_insight_3": content_ko.get("key_insight_3", ""),
            "news_summaries": content_ko.get("news_summaries", [])
        }
        print("EN content fallback applied")

    print("Step 4: Collecting stock picks...")
    stock_data = None
    if STOCK_ENABLED:
        try:
            stock_data = get_stock_picks()
            print("Stock picks collected")
        except Exception as e:
            print(f"Stock picks error: {e}")

    print("Step 5: Building HTML...")
    today     = now_kst().strftime("%Y년 %m월 %d일")
    today_num = now_kst().strftime("%Y%m%d")

    filename_ko = build_html(news_list, content_ko, stock_data, lang="ko")

    try:
        filename_en = build_html(news_list, content_en, stock_data, lang="en")
    except Exception as e:
        print(f"EN HTML build failed: {e}")
        filename_en = None

    print("Step 6: Building archives...")
    build_archive(lang="ko")
    try:
        build_archive(lang="en")
    except Exception as e:
        print(f"EN archive build failed: {e}")

    print("Step 7: Building sitemap...")
    build_sitemap()

    print("Step 8: Pushing to GitHub...")
    import os as _os
    files_to_push = [
        "index.html",
        "archive.html",
        f"briefing_{today_num}.html",
        "sitemap.xml",
        "robots.txt"
    ]
    # EN 파일이 실제로 생성된 경우에만 push
    if _os.path.exists("index_en.html"):
        files_to_push.append("index_en.html")
    if _os.path.exists("archive_en.html"):
        files_to_push.append("archive_en.html")
    en_briefing = f"briefing_en_{today_num}.html"
    if _os.path.exists(en_briefing):
        files_to_push.append(en_briefing)
    push_to_github(files_to_push)

    print("Step 9: Sending Telegram...")
    send_telegram(today, filename_ko)

    print("All done!")
