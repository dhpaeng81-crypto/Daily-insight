import feedparser
import requests
from openai import OpenAI
from datetime import datetime
import re
import os
 
# =====================
# 설정값
# =====================
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
 
# =====================
# RSS 피드
# =====================
RSS_FEEDS = [
    ("Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Finance", "https://www.hankyung.com/feed/finance"),
    ("AI/IT", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Energy", "https://feeds.reuters.com/reuters/businessNews"),
    ("Energy", "https://www.google.com/alerts/feeds/05107057229753784254/4810996089673190473")
]
 
# =====================
# 이미지 추출
# =====================
def extract_image(entry):
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        return entry.media_thumbnail[0].get("url", "")
    if hasattr(entry, "media_content") and entry.media_content:
        return entry.media_content[0].get("url", "")
    if hasattr(entry, "enclosures") and entry.enclosures:
        for enc in entry.enclosures:
            if "image" in enc.get("type", ""):
                return enc.get("url", "")
    summary = entry.get("summary", "")
    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    if img_match:
        return img_match.group(1)
    return ""
 
# =====================
# RSS 수집
# =====================
def collect_news():
    all_news = []
    for category, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get("title", url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "")
                summary = re.sub('<[^>]+>', '', entry.get("summary", ""))[:200]
                link = entry.get("link", "")
                image = extract_image(entry)
                all_news.append({
                    "category": category,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "image": image,
                    "source": source_name
                })
            print(f"OK: {category} - {len(feed.entries)} articles")
        except Exception as e:
            print(f"Error ({url}): {e}")
    return all_news
 
# =====================
# 단일 뉴스 한국어 번역 (백업용)
# =====================
def translate_single(news_item):
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "한국어 번역가입니다. 반드시 한국어로만 답하세요."
            },
            {
                "role": "user",
                "content": f"아래 뉴스 제목과 내용을 한국어로 번역하고 2-3문장으로 요약해주세요.\n\n제목: {news_item['title']}\n내용: {news_item['summary']}"
            }
        ],
        max_tokens=300
    )
    return {
        "title": news_item["title"],
        "body": response.choices[0].message.content
    }
 
# =====================
# OpenAI 요약
# =====================
def generate_content(news_list):
    client = OpenAI(api_key=OPENAI_API_KEY)
 
    news_text = ""
    for i, n in enumerate(news_list):
        news_text += f"[index:{i}][{n['category']}] {n['title']}\n{n['summary']}\n\n"
 
    prompt = f"""
당신은 금융,IT,에너지 투자 전문가이자 한국어 전문 뉴스 에디터입니다.
아래 뉴스를 바탕으로 Daily Insight 웹진 콘텐츠를 작성해주세요.
독자는 한국인 투자자와 일반인입니다.
 
[절대 규칙]
- 모든 출력은 반드시 한국어로만 작성할 것
- 영어 단어가 포함되면 안 됨 (고유명사 제외: 회사명, 인명 등)
- 전문용어는 쉬운 한국어로 풀어서 설명할 것
- 왜 중요한지 맥락을 포함할 것
- 인사이트는 구체적인 방향성이나 수치, 시장변화 등을 다루며, 단기/중기 시장 방향성, 영향에 속하는 산업군이나 기업 등을 포함하여 풍부하게 제시할 것 
- news_summaries는 반드시 수집된 모든 뉴스를 포함할 것
- original_index는 뉴스 데이터의 [index:숫자] 값과 정확히 일치할 것
- 반드시 아래 JSON 형식으로만 응답할 것 (다른 텍스트 없이)
 
{{
  "hero_title": "오늘의 핵심 헤드라인 100자 이내 한국어",
  "hero_desc": "오늘 브리핑 전체를 관통하는 한 줄 요약 100자 이내 한국어",
  "finance_overview": "금융 시장 전반 흐름 2-3문장 한국어",
  "finance_comment": "투자자 관점 인사이트 3-4문장 한국어",
  "tech_overview": "AI/IT 트렌드 전반 흐름 2-3문장 한국어",
  "tech_comment": "IT/투자 관점 인사이트 3-4문장 한국어",
  "energy_overview": "에너지 시장 전반 흐름 2-3문장 한국어",
  "energy_comment": "에너지/투자 관점 인사이트 3-4문장 한국어",
  "key_insight_1": "오늘의 핵심 인사이트 1 100자 이내 한국어",
  "key_insight_2": "오늘의 핵심 인사이트 2 100자 이내 한국어",
  "key_insight_3": "오늘의 핵심 인사이트 3 100자 이내 한국어",
  "news_summaries": [
    {{
      "category": "Finance 또는 AI/IT 또는 Energy",
      "title": "뉴스 제목 한국어로 번역",
      "body": "2-3문장 해설 한국어로 (왜 중요한지 포함)",
      "original_index": 0
    }}
  ]
}}
 
뉴스 데이터:
{news_text}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "당신은 한국어 전문 뉴스레터 에디터입니다. 모든 출력은 반드시 한국어로만 작성해야 합니다. 영어로 작성하면 절대 안 됩니다."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=4000
    )
 
    import json
    text = response.choices[0].message.content
    text = re.sub(r'```json|```', '', text).strip()
    return json.loads(text)
 
# =====================
# 뉴스 카드 HTML 생성
# =====================
def make_news_card(news_item, summary, category_class):
    if news_item["image"]:
        image_html = f'''<div class="news-thumb">
        <img src="{news_item['image']}" alt="" onerror="this.parentElement.innerHTML='<div class=news-thumb-placeholder>📰</div>'">
      </div>'''
    else:
        image_html = '<div class="news-thumb"><div class="news-thumb-placeholder">📰</div></div>'
 
    return f'''
    <div class="news-card">
      {image_html}
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
# 최종 HTML 생성
# =====================
def build_html(news_list, content):
    today = datetime.now().strftime("%Y년 %m월 %d일")
    today_num = datetime.now().strftime("%Y%m%d")
 
    finance_news = [n for n in news_list if n["category"] == "Finance"]
    tech_news = [n for n in news_list if n["category"] == "AI/IT"]
    energy_news = [n for n in news_list if n["category"] == "Energy"]
 
    summaries = content.get("news_summaries", [])
 
    # 인덱스 기반 매핑
    summaries_by_index = {}
    for s in summaries:
        idx = s.get("original_index")
        if idx is not None:
            summaries_by_index[idx] = s
 
    # 제목 기반 매핑 (백업)
    summaries_by_title = {}
    for s in summaries:
        summaries_by_title[s.get("title", "").lower()] = s
 
    def get_summary(idx):
        # 1순위: 인덱스로 매핑
        if idx in summaries_by_index:
            return summaries_by_index[idx]
        # 2순위: 제목 유사도로 매핑
        orig_title = news_list[idx]["title"].lower()
        for title, s in summaries_by_title.items():
            words = title.split()[:3]
            if words and any(word in orig_title for word in words):
                return s
        # 3순위: 단독 번역 요청
        print(f"Translating index {idx} individually...")
        return translate_single(news_list[idx])
 
    finance_cards = ""
    for n in finance_news[:3]:
        orig_idx = news_list.index(n)
        finance_cards += make_news_card(n, get_summary(orig_idx), "finance")
 
    tech_cards = ""
    for n in tech_news[:3]:
        orig_idx = news_list.index(n)
        tech_cards += make_news_card(n, get_summary(orig_idx), "tech")
 
    energy_cards = ""
    for n in energy_news[:3]:
        orig_idx = news_list.index(n)
        energy_cards += make_news_card(n, get_summary(orig_idx), "energy")
 
    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Insight — {today}</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Noto+Sans+KR:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root {{
  --ink: #18181b; --ink-soft: #52525b; --ink-muted: #a1a1aa;
  --bg: #fafaf9; --bg-card: #ffffff; --bg-subtle: #f4f4f5;
  --accent: #0f766e; --accent-light: #ccfbf1;
  --finance: #0369a1; --finance-bg: #e0f2fe;
  --tech: #6d28d9; --tech-bg: #ede9fe;
  --energy: #b45309; --energy-bg: #fef3c7;
  --border: #e4e4e7; --radius: 12px;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--ink); font-family: "Noto Sans KR", sans-serif; font-weight: 300; line-height: 1.8; }}
a {{ color: inherit; text-decoration: none; }}
.site-header {{ border-bottom: 1px solid var(--border); background: var(--bg-card); position: sticky; top: 0; z-index: 100; }}
.header-inner {{ max-width: 780px; margin: 0 auto; padding: 0 24px; height: 56px; display: flex; align-items: center; justify-content: space-between; }}
.logo {{ font-family: "Playfair Display", serif; font-size: 20px; font-weight: 700; }}
.logo span {{ color: var(--accent); }}
.header-meta {{ font-size: 12px; color: var(--ink-muted); }}
.hero {{ max-width: 780px; margin: 0 auto; padding: 56px 24px 40px; border-bottom: 1px solid var(--border); }}
.issue-badge {{ display: inline-flex; align-items: center; font-size: 11px; font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent); background: var(--accent-light); padding: 4px 12px; border-radius: 100px; margin-bottom: 20px; }}
.hero-title {{ font-family: "Playfair Display", serif; font-size: clamp(26px, 5vw, 40px); font-weight: 700; line-height: 1.2; letter-spacing: -0.02em; margin-bottom: 16px; }}
.hero-desc {{ font-size: 16px; color: var(--ink-soft); max-width: 560px; margin-bottom: 24px; line-height: 1.7; }}
.hero-tags {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.tag {{ font-size: 12px; font-weight: 500; padding: 4px 12px; border-radius: 100px; border: 1px solid var(--border); color: var(--ink-soft); }}
.main {{ max-width: 780px; margin: 0 auto; padding: 48px 24px 80px; }}
.section-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1.5px solid var(--border); }}
.section-pill {{ font-size: 11px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; padding: 4px 10px; border-radius: 6px; }}
.section-pill.finance {{ background: var(--finance-bg); color: var(--finance); }}
.section-pill.tech {{ background: var(--tech-bg); color: var(--tech); }}
.section-pill.energy {{ background: var(--energy-bg); color: var(--energy); }}
.section-title {{ font-family: "Playfair Display", serif; font-size: 20px; font-weight: 700; }}
.section-overview {{ font-size: 15px; color: var(--ink-soft); line-height: 1.75; margin-bottom: 24px; padding: 16px 20px; background: var(--bg-subtle); border-left: 3px solid var(--border); border-radius: 0 8px 8px 0; }}
.news-list {{ display: flex; flex-direction: column; gap: 16px; margin-bottom: 24px; }}
.news-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; display: grid; grid-template-columns: 120px 1fr; }}
.news-thumb {{ width: 120px; min-height: 110px; overflow: hidden; background: var(--bg-subtle); }}
.news-thumb img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
.news-thumb-placeholder {{ width: 100%; height: 100%; min-height: 110px; display: flex; align-items: center; justify-content: center; font-size: 28px; opacity: 0.3; }}
.news-content {{ padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }}
.news-source-row {{ display: flex; align-items: center; justify-content: space-between; }}
.news-source {{ font-size: 11px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-muted); }}
.news-category-dot {{ width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 5px; }}
.news-category-dot.finance {{ background: var(--finance); }}
.news-category-dot.tech {{ background: var(--tech); }}
.news-category-dot.energy {{ background: var(--energy); }}
.news-title {{ font-size: 14px; font-weight: 500; line-height: 1.45; color: var(--ink); }}
.news-title a:hover {{ color: var(--accent); }}
.news-body {{ font-size: 13px; color: var(--ink-soft); line-height: 1.7; }}
.read-more {{ font-size: 12px; font-weight: 500; color: var(--accent); margin-top: 4px; display: inline-flex; align-items: center; gap: 3px; }}
.editor-note {{ background: var(--bg-subtle); border-radius: 10px; padding: 16px 20px; margin-bottom: 48px; display: flex; gap: 12px; }}
.editor-icon {{ font-size: 18px; flex-shrink: 0; margin-top: 2px; }}
.editor-label {{ font-size: 11px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; color: var(--accent); margin-bottom: 4px; }}
.editor-text {{ font-size: 14px; color: var(--ink-soft); line-height: 1.7; }}
.section-divider {{ height: 1px; background: var(--border); margin: 0 0 48px; }}
.summary-box {{ background: var(--ink); color: #fff; border-radius: var(--radius); padding: 32px 36px; margin-bottom: 48px; }}
.summary-label {{ font-size: 11px; font-weight: 500; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent-light); margin-bottom: 20px; }}
.summary-title {{ font-family: "Playfair Display", serif; font-size: 22px; font-weight: 700; color: #fff; margin-bottom: 20px; }}
.summary-list {{ list-style: none; display: flex; flex-direction: column; gap: 14px; }}
.summary-list li {{ display: grid; grid-template-columns: 28px 1fr; gap: 12px; font-size: 14px; color: #d4d4d8; line-height: 1.65; }}
.summary-num {{ font-family: "Playfair Display", serif; font-size: 22px; color: var(--accent-light); line-height: 1.1; opacity: 0.6; }}
.site-footer {{ border-top: 1px solid var(--border); padding: 32px 24px; text-align: center; }}
.footer-inner {{ max-width: 780px; margin: 0 auto; }}
.footer-logo {{ font-family: "Playfair Display", serif; font-size: 16px; font-weight: 700; margin-bottom: 8px; }}
.footer-logo span {{ color: var(--accent); }}
.footer-desc {{ font-size: 12px; color: var(--ink-muted); margin-bottom: 16px; }}
.footer-links {{ display: flex; justify-content: center; gap: 20px; font-size: 12px; color: var(--ink-muted); }}
@media (min-width: 1024px) {{
  .header-inner {{ max-width: 1080px; padding: 0 48px; }}
  .hero {{ max-width: 1080px; padding: 72px 48px 56px; }}
  .main {{ max-width: 1080px; padding: 56px 48px 100px; }}
  .hero-title {{ font-size: 52px; }}
  .hero-desc {{ font-size: 18px; max-width: 680px; }}
  .section-title {{ font-size: 24px; }}
  .section-overview {{ font-size: 17px; }}
  .news-card {{ grid-template-columns: 160px 1fr; }}
  .news-thumb {{ width: 160px; min-height: 140px; }}
  .news-title {{ font-size: 16px; }}
  .news-body {{ font-size: 15px; }}
  .editor-text {{ font-size: 16px; }}
  .summary-box {{ padding: 40px 48px; }}
  .summary-title {{ font-size: 26px; }}
  .summary-list li {{ font-size: 16px; }}
  .footer-inner {{ max-width: 1080px; }}
}}
@media (max-width: 600px) {{
  .hero {{ padding: 36px 20px 32px; }}
  .main {{ padding: 36px 20px 60px; }}
  .news-card {{ grid-template-columns: 1fr; }}
  .news-thumb {{ width: 100%; height: 160px; }}
  .summary-box {{ padding: 24px 20px; }}
  .header-meta {{ display: none; }}
}}
</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <div class="logo">Daily<span>Insight</span></div>
    <div class="header-meta">{today}</div>
  </div>
</header>
 
<section class="hero">
  <div class="issue-badge">오늘의 브리핑</div>
  <h1 class="hero-title">{content.get("hero_title", "오늘의 Daily Insight")}</h1>
  <p class="hero-desc">{content.get("hero_desc", "")}</p>
  <div class="hero-tags">
    <span class="tag">💹 금융 시장</span>
    <span class="tag">🤖 AI · IT</span>
    <span class="tag">⚡ 에너지</span>
  </div>
</section>
 
<main class="main">
  <div class="section-header">
    <span class="section-pill finance">Finance</span>
    <span class="section-title">금융 시장</span>
  </div>
  <p class="section-overview">{content.get("finance_overview", "")}</p>
  <div class="news-list">{finance_cards}</div>
  <div class="editor-note">
    <div class="editor-icon">💡</div>
    <div>
      <div class="editor-label">에디터 인사이트</div>
      <div class="editor-text">{content.get("finance_comment", "")}</div>
    </div>
  </div>
  <div class="section-divider"></div>
 
  <div class="section-header">
    <span class="section-pill tech">Tech</span>
    <span class="section-title">AI · IT 트렌드</span>
  </div>
  <p class="section-overview">{content.get("tech_overview", "")}</p>
  <div class="news-list">{tech_cards}</div>
  <div class="editor-note">
    <div class="editor-icon">💡</div>
    <div>
      <div class="editor-label">에디터 인사이트</div>
      <div class="editor-text">{content.get("tech_comment", "")}</div>
    </div>
  </div>
  <div class="section-divider"></div>
 
  <div class="section-header">
    <span class="section-pill energy">Energy</span>
    <span class="section-title">에너지 · 산업</span>
  </div>
  <p class="section-overview">{content.get("energy_overview", "")}</p>
  <div class="news-list">{energy_cards}</div>
  <div class="editor-note">
    <div class="editor-icon">💡</div>
    <div>
      <div class="editor-label">에디터 인사이트</div>
      <div class="editor-text">{content.get("energy_comment", "")}</div>
    </div>
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
</main>
 
<footer class="site-footer">
  <div class="footer-inner">
    <div class="footer-logo">Daily<span>Insight</span></div>
    <div class="footer-desc">매일 오전 7시, 투자자를 위한 핵심 인사이트</div>
    <div class="footer-links">
      <a href="index.html">아카이브</a>
    </div>
  </div>
</footer>
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
 
# =====================
# 텔레그램 발송
# =====================
def send_telegram(today, filename):
    site_url = "https://dhpaeng81-crypto.github.io/Daily-insight"
    message = (
        f"*Daily Insight* 발행 완료\n"
        f"{today}\n\n"
        f"👉 [오늘의 브리핑 보기]({site_url})"
    )
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
    )
    print("Telegram: OK")
 
# =====================
# 실행
# =====================
if __name__ == "__main__":
    print("Step 1: Collecting news...")
    news_list = collect_news()
    print(f"Total: {len(news_list)} articles")
 
    print("Step 2: Generating content...")
    content = generate_content(news_list)
    print("Content generated")
 
    print("Step 3: Building HTML...")
    today = datetime.now().strftime("%Y년 %m월 %d일")
    filename = build_html(news_list, content)
 
    print("Step 4: Sending Telegram...")
    send_telegram(today, filename)
 
    print("All done!")
