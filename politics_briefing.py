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

# =====================
# 설정값
# =====================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# 한국시간 (KST = UTC+9)
KST = timezone(timedelta(hours=9))
def now_kst():
    return datetime.now(KST)
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# =====================
# 기본 이미지 풀
# =====================
DEFAULT_IMAGES = {
    "Politics": [
        "https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800&q=80",
        "https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=800&q=80",
        "https://images.unsplash.com/photo-1569025743873-ea3a9ade89f9?w=800&q=80",
        "https://images.unsplash.com/photo-1606761568499-6d2451b23c66?w=800&q=80",
        "https://images.unsplash.com/photo-1555848962-6e79363ec58f?w=800&q=80",
    ],
    "International": [
        "https://images.unsplash.com/photo-1526470608268-f674ce90ebd4?w=800&q=80",
        "https://images.unsplash.com/photo-1493246507139-91e8fad9978e?w=800&q=80",
        "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=800&q=80",
        "https://images.unsplash.com/photo-1508739773434-c26b3d09e071?w=800&q=80",
        "https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=800&q=80",
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
    return random.choice(DEFAULT_IMAGES.get(category, DEFAULT_IMAGES["Politics"]))

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
# RSS 피드 — 보수 성향 소스
# =====================
RSS_FEEDS = [
    ("Politics", "https://www.chosun.com/arc/outboundfeeds/rss/category/politics/"),
    ("Politics", "http://rss.donga.com/politics.xml"),
    ("Politics", "http://rss.donga.com/editorials.xml"),
    ("Politics", "https://www.munhwa.com/rss/politics.xml"),
    ("International", "https://www.rfa.org/korean/rss2.xml"),
    ("International", "https://www.voakorea.com/api/z_mpetyitop"),
    ("Politics", "https://www.newdaily.co.kr/site/data/rss/rss.xml"),        # 뉴데일리
    ("Politics", "https://www.pennmike.com/rss/allArticle.xml"),              # 펜앤드마이크
    ("International", "https://thediplomat.com/feed/"),                       # The Diplomat
    ("International", "https://warontherocks.com/feed/"),                     # War on the Rocks
    ("International", "https://www.38north.org/feed/"),                       # 38North (북한)
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
    is_sunday = now_kst().weekday() == 6

    news_text = ""
    for i, n in enumerate(news_list):
        news_text += f"[index:{i}][{n['category']}] {n['title']}\n{n['summary']}\n\n"

    depth_instruction = """
오늘은 일요일입니다. 주간 심층 분석 모드로 작성해주세요.
- 이번 주 주요 사건들의 역사적 맥락과 구조적 의미 심층 분석
- 과거 유사 사례와의 비교 분석 (구체적 연도, 인물, 사건 포함)
- 중장기적 관점의 전망과 시사점
- 각 섹션을 평소보다 2배 이상 깊이 있게 작성
""" if is_sunday else """
오늘은 평일입니다. 데일리 브리핑 모드로 작성해주세요.
- 오늘의 핵심 뉴스 요약과 보수적 관점의 분석
- 간결하고 명확한 인사이트 제공
"""

    prompt = f"""
당신은 대한민국 헌법적 가치와 자유민주주의를 수호하는 20년 경력의 역사학자이자 정치 평론가입니다.
아래 뉴스를 바탕으로 역사·정치 브리핑 콘텐츠를 작성해주세요.

{depth_instruction}

[편집 원칙]
1. 대한민국 건국 정통성(1948년 건국)과 자유민주주의 헌법 가치를 기준으로 분석
2. 역사적 사실과 1차 사료, 통계, 공식 기록에 근거한 객관적 서술
3. 좌파·진보 진영의 주장도 소개하되, 팩트에 근거한 명확한 반론 제시
4. 한미동맹 강화와 자유진영 연대 관점에서 국제 정세 해석
5. 선동적·감정적 표현 배제, 논리와 근거 중심
6. 주류 진보 언론의 프레임과 다른 보수적 시각 제시
7. 역사적 선례: 현재 사건과 유사한 과거 사례 구체적으로 언급
8. 모든 출력은 반드시 한국어로만 작성
9. news_summaries는 수집된 모든 뉴스 포함
10. original_index는 [index:숫자] 값과 정확히 일치
11. 반드시 아래 JSON 형식으로만 응답 (다른 텍스트 없이)

{{
  "hero_title": "오늘의 핵심 헤드라인 25자 이내",
  "hero_desc": "오늘 브리핑의 핵심 메시지 60자 이내",
  "today_summary": "오늘의 정치 지형 전반 요약 3-4문장. 헌법적 가치 관점에서의 현 상황 진단",
  "politics_overview": "국내 정치 현안 흐름 3-4문장. 주요 이슈의 본질과 헌법적 의미 분석",
  "politics_comment": "보수 관점 핵심 인사이트 4-5문장. 역사적 선례, 팩트 근거, 진보 주장에 대한 반론, 자유민주주의 관점의 평가 포함",
  "international_overview": "국제 정세 흐름 3-4문장. 한미동맹·자유진영 관점에서의 분석",
  "international_comment": "지정학적 인사이트 4-5문장. 한국의 국익 관점, 역사적 맥락, 안보 리스크 포함",
  "history_insight": "오늘 이슈와 연결되는 역사적 교훈 4-5문장. 구체적인 역사적 사례와 날짜, 인물 반드시 포함",
  "key_insight_1": "핵심 인사이트 1: 오늘의 가장 중요한 정치적 함의 (구체적 근거 포함)",
  "key_insight_2": "핵심 인사이트 2: 국제 관계나 안보 관점의 핵심 메시지",
  "key_insight_3": "핵심 인사이트 3: 역사적 교훈이나 향후 주목해야 할 포인트",
  "news_summaries": [
    {{
      "category": "Politics 또는 International",
      "title": "뉴스 제목 한국어로",
      "body": "3문장: 사실 요약, 헌법적/역사적 의미, 자유민주주의 관점 평가",
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
            {
                "role": "system",
                "content": "당신은 대한민국 헌법적 가치와 자유민주주의를 수호하는 역사학자이자 정치 평론가입니다. 모든 분석은 반드시 한국어로 작성하세요."
            },
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
      btn.parentElement.style.background = '#7c3aed';
      btn.parentElement.style.color = '#fff';
      btn.parentElement.style.borderColor = '#7c3aed';
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
  --ink: #1a1a2e; --ink-soft: #4a4a6a; --ink-muted: #9a9ab0;
  --bg: #f8f8fc; --bg-card: #ffffff; --bg-subtle: #f0f0f8;
  --accent: #7c3aed; --accent-light: #ede9fe;
  --politics: #1e40af; --politics-bg: #dbeafe;
  --international: #065f46; --international-bg: #d1fae5;
  --history: #92400e; --history-bg: #fef3c7;
  --border: #e0e0f0; --radius: 12px;
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
    b = "active" if active == "briefing" else ""
    a = "active" if active == "archive" else ""
    return f'''
<header class="site-header">
  <div class="header-inner">
    <div class="logo"><a href="politics_index.html">Korea<span>Insight</span></a></div>
    <nav class="header-nav">
      <a href="politics_index.html" class="{b}">역사·정치</a>
      <a href="politics_archive.html" class="{a}">아카이브</a>
      <div class="divider"></div>
      <a href="index.html">금융·AI·에너지</a>
    </nav>
  </div>
</header>'''

def get_footer_html():
    return '''
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-logo">Korea<span>Insight</span></div>
    <div class="footer-desc">자유민주주의 가치 기반의 역사·정치 브리핑</div>
    <div class="footer-links">
      <a href="politics_index.html">역사·정치 브리핑</a>
      <a href="politics_archive.html">아카이브</a>
      <a href="index.html">Daily Insight (금융·AI·에너지)</a>
    </div>
  </div>
</footer>'''

def build_html(news_list, content):
    today = now_kst().strftime("%Y년 %m월 %d일")
    today_num = now_kst().strftime("%Y%m%d")
    is_sunday = now_kst().weekday() == 6
    issue_label = "주간 심층 분석" if is_sunday else "오늘의 브리핑"

    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    page_url = f"{site_url}/politics_index.html"

    politics_news = [n for n in news_list if n["category"] == "Politics"]
    international_news = [n for n in news_list if n["category"] == "International"]

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

    politics_cards = "".join([make_news_card(n, get_summary(news_list.index(n)), "politics") for n in politics_news[:3]])
    international_cards = "".join([make_news_card(n, get_summary(news_list.index(n)), "international") for n in international_news[:3]])

    hero_title = content.get("hero_title", "오늘의 KoreaInsight")
    hero_desc = content.get("hero_desc", "자유민주주의 관점의 역사·정치 브리핑")
    share_buttons = get_share_buttons_html(hero_title, page_url)
    common_css = get_common_css()

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KoreaInsight — {today}</title>
<meta property="og:title" content="KoreaInsight — {today}">
<meta property="og:description" content="{hero_desc}">
<meta property="og:image" content="https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?w=800&q=80">
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
.today-summary {{ max-width: 780px; margin: 0 auto; padding: 24px 24px 0; }}
.today-summary-box {{ background: var(--ink); color: #fff; border-radius: var(--radius); padding: 24px 28px; }}
.today-summary-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-light); margin-bottom: 10px; }}
.today-summary-text {{ font-size: 15px; line-height: 1.8; color: #d4d4e8; }}
.main {{ max-width: 780px; margin: 0 auto; padding: 48px 24px 80px; }}
.section-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1.5px solid var(--border); }}
.section-pill {{ font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; padding: 4px 10px; border-radius: 6px; }}
.section-pill.politics {{ background: var(--politics-bg); color: var(--politics); }}
.section-pill.international {{ background: var(--international-bg); color: var(--international); }}
.section-pill.history {{ background: var(--history-bg); color: var(--history); }}
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
.news-category-dot.politics {{ background: var(--politics); }}
.news-category-dot.international {{ background: var(--international); }}
.news-title {{ font-size: 15px; font-weight: 700; line-height: 1.45; color: var(--ink); }}
.news-title a:hover {{ color: var(--accent); }}
.news-body {{ font-size: 13px; color: var(--ink-soft); line-height: 1.7; }}
.read-more {{ font-size: 12px; font-weight: 700; color: var(--accent); margin-top: 4px; display: inline-flex; align-items: center; gap: 3px; }}
.analyst-note {{ background: var(--bg-card); border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 0 10px 10px 0; padding: 20px 24px; margin-bottom: 48px; }}
.analyst-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); margin-bottom: 8px; }}
.analyst-text {{ font-size: 14px; color: var(--ink); line-height: 1.85; }}
.history-box {{ background: var(--history-bg); border: 1px solid #fcd34d; border-radius: var(--radius); padding: 24px 28px; margin-bottom: 48px; }}
.history-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--history); margin-bottom: 10px; }}
.history-text {{ font-size: 14px; color: #78350f; line-height: 1.85; }}
.section-divider {{ height: 1px; background: var(--border); margin: 0 0 48px; }}
.summary-box {{ background: var(--ink); color: #fff; border-radius: var(--radius); padding: 32px 36px; margin-bottom: 48px; }}
.summary-label {{ font-size: 11px; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent-light); margin-bottom: 20px; }}
.summary-title {{ font-family: var(--font); font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 20px; }}
.summary-list {{ list-style: none; display: flex; flex-direction: column; gap: 14px; }}
.summary-list li {{ display: grid; grid-template-columns: 28px 1fr; gap: 12px; font-size: 14px; color: #d4d4d8; line-height: 1.65; }}
.summary-num {{ font-family: var(--font); font-size: 20px; font-weight: 800; color: var(--accent-light); line-height: 1.2; opacity: 0.6; }}
.share-section {{ border-top: 1px solid var(--border); padding-top: 32px; margin-bottom: 48px; text-align: center; }}
.share-label {{ font-size: 12px; color: var(--ink-muted); letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700; margin-bottom: 16px; }}
.share-buttons {{ display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; }}
.share-btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 10px 24px; border-radius: 100px; font-size: 13px; font-weight: 700; cursor: pointer; border: none; transition: transform 0.15s, box-shadow 0.15s; font-family: var(--font); text-decoration: none; }}
.share-btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
.share-btn.twitter {{ background: #000; color: #fff; }}
.share-btn.copy {{ background: var(--bg-subtle); color: var(--ink); border: 1px solid var(--border); transition: transform 0.15s, box-shadow 0.15s, background 0.2s, color 0.2s, border-color 0.2s; }}
@media (min-width: 1024px) {{
  .hero {{ max-width: 1080px; padding: 72px 48px 56px; }}
  .today-summary {{ max-width: 1080px; padding: 24px 48px 0; }}
  .main {{ max-width: 1080px; padding: 56px 48px 100px; }}
  .hero-title {{ font-size: 48px; }}
  .hero-desc {{ font-size: 18px; max-width: 680px; }}
  .section-title {{ font-size: 24px; }}
  .section-overview {{ font-size: 16px; }}
  .news-list {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
  .news-thumb {{ height: 180px; }}
  .analyst-text {{ font-size: 15px; }}
  .history-text {{ font-size: 15px; }}
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
  .today-summary {{ padding: 20px 20px 0; }}
  .main {{ padding: 36px 20px 60px; }}
  .summary-box {{ padding: 24px 20px; }}
  .share-btn {{ padding: 9px 18px; font-size: 12px; }}
}}
</style>
</head>
<body>
{get_header_html("briefing")}

<section class="hero">
  <div class="issue-badge">{issue_label}</div>
  <h1 class="hero-title">{hero_title}</h1>
  <p class="hero-desc">{hero_desc}</p>
  <div class="hero-tags">
    <span class="tag">🏛️ 국내 정치</span>
    <span class="tag">🌐 국제 정세</span>
    <span class="tag">📜 역사적 맥락</span>
  </div>
</section>

<div class="today-summary">
  <div class="today-summary-box">
    <div class="today-summary-label">📋 오늘의 정치 지형</div>
    <div class="today-summary-text">{content.get("today_summary", "")}</div>
  </div>
</div>

<main class="main">
  <div class="section-header">
    <span class="section-pill politics">Politics</span>
    <span class="section-title">국내 정치</span>
  </div>
  <p class="section-overview">{content.get("politics_overview", "")}</p>
  <div class="news-list">{politics_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">🔍 보수적 관점 분석</div>
    <div class="analyst-text">{content.get("politics_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="section-header">
    <span class="section-pill international">International</span>
    <span class="section-title">국제 정세</span>
  </div>
  <p class="section-overview">{content.get("international_overview", "")}</p>
  <div class="news-list">{international_cards}</div>
  <div class="analyst-note">
    <div class="analyst-label">🔍 지정학적 분석</div>
    <div class="analyst-text">{content.get("international_comment", "")}</div>
  </div>
  <div class="section-divider"></div>

  <div class="section-header">
    <span class="section-pill history">History</span>
    <span class="section-title">역사적 교훈</span>
  </div>
  <div class="history-box">
    <div class="history-label">📜 오늘의 이슈, 역사에서 배운다</div>
    <div class="history-text">{content.get("history_insight", "")}</div>
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
  {share_buttons}
</main>

{get_footer_html()}
</body>
</html>'''

    filename = f"politics_{today_num}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML saved: {filename}")
    with open("politics_index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("politics_index.html updated")
    return filename

def build_archive():
    files = sorted(glob.glob("politics_2*.html"), reverse=True)
    archive_items = ""
    for f in files:
        date_str = f.replace("politics_", "").replace(".html", "")
        try:
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            date_display = date_obj.strftime("%Y년 %m월 %d일")
            weekday = ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]
            is_sunday_file = date_obj.weekday() == 6
            with open(f, "r", encoding="utf-8") as fp:
                html_content = fp.read()
            title_match = re.search(r'<h1 class="hero-title">(.*?)</h1>', html_content, re.DOTALL)
            hero_title = title_match.group(1).strip() if title_match else "KoreaInsight 브리핑"
            is_today = date_str == now_kst().strftime("%Y%m%d")
            today_badge = '<span class="today-badge">오늘</span>' if is_today else ''
            sunday_badge = '<span class="sunday-badge">심층분석</span>' if is_sunday_file else ''
            archive_items += f'''
      <a href="{f}" class="archive-card">
        <div class="archive-date">
          <span class="archive-date-num">{date_obj.strftime("%m.%d")}</span>
          <span class="archive-weekday">{weekday}요일</span>
        </div>
        <div class="archive-info">
          <div class="archive-title">{hero_title} {today_badge}{sunday_badge}</div>
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
<title>KoreaInsight — 아카이브</title>
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
.sunday-badge {{ font-size: 10px; font-weight: 800; background: var(--history); color: #fff; padding: 2px 8px; border-radius: 100px; }}
@media (min-width: 1024px) {{ .archive-hero {{ max-width: 1080px; padding: 72px 48px 56px; }} .archive-main {{ max-width: 1080px; padding: 40px 48px 100px; }} }}
@media (max-width: 600px) {{ .archive-hero {{ padding: 36px 20px 32px; }} .archive-main {{ padding: 32px 20px 60px; }} .archive-card {{ grid-template-columns: 52px 1fr auto; gap: 12px; padding: 14px 16px; }} }}
</style>
</head>
<body>
{get_header_html("archive")}
<section class="archive-hero">
  <div class="archive-hero-label">아카이브</div>
  <h1 class="archive-hero-title">지난 브리핑 모아보기</h1>
  <p class="archive-hero-desc">자유민주주의 관점의 역사·정치 브리핑을 날짜별로 확인하세요. 매주 일요일은 주간 심층 분석입니다.</p>
</section>
<main class="archive-main">
  <div class="archive-count">총 {len(files)}개의 브리핑</div>
  <div class="archive-list">{archive_items}</div>
</main>
{get_footer_html()}
</body>
</html>'''

    with open("politics_archive.html", "w", encoding="utf-8") as f:
        f.write(archive_html)
    print("politics_archive.html updated")

# =====================
# GitHub Pages 업로드
# =====================
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

# =====================
# 텔레그램 발송
# =====================
def send_telegram(today, filename):
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    is_sunday = now_kst().weekday() == 6
    label = "주간 심층 분석" if is_sunday else "역사·정치 브리핑"
    message = f"*KoreaInsight* {label} 발행\n{today}\n\n👉 [브리핑 보기]({site_url}/politics_index.html)"
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
    print("Step 2: Generating content...")
    content = generate_content(news_list)
    print("Content generated")
    print("Step 3: Building HTML...")
    today = now_kst().strftime("%Y년 %m월 %d일")
    today_num = now_kst().strftime("%Y%m%d")
    filename = build_html(news_list, content)
    print("Step 4: Building archive...")
    build_archive()
    print("Step 5: Pushing to GitHub...")
    push_to_github([
        "politics_index.html",
        "politics_archive.html",
        f"politics_{today_num}.html"
    ])
    print("Step 6: Sending Telegram...")
    send_telegram(today, filename)
    print("All done!")
