import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
}

DASHBOARD_URL = "https://rmadh6418-ai.github.io/stock-dashboard/"

EXCLUDE_NEWS_KEYWORDS = [
    "콘서트", "포크", "음악회", "축제", "페스티벌", "공연", "전시회", "문화",
    "봉사", "기부", "나눔", "장학", "사회공헌", "바자회", "캠페인", "후원",
    "부고", "부음", "화혼", "결혼", "인사", "동정", "알림", "모집", "채용",
    "이벤트", "경품", "할인", "프로모션", "쿠폰", "체험단", "선착순", "추첨",
    "골프대회", "마라톤", "시상식", "장학금", "헌혈", "가을", "여행", "맛집",
    "포토", "영상", "방송", "예능"
]

BUSINESS_NEWS_KEYWORDS = [
    "실적", "매출", "영업익", "영업이익", "순이익", "수주", "계약", "투자", "공급",
    "인수", "합병", "M&A", "증설", "공시", "주가", "상승", "하락", "급등", "급락",
    "수출", "양산", "출시", "기술", "개발", "협력", "제휴", "공장", "가동", "수혜",
    "흑자", "적자", "전망", "목표가", "배당", "지분", "증자", "특허", "사업", "성장",
    "솔루션", "생산", "상장", "신제품", "AI", "반도체", "배터리", "로봇", "방산",
    "원전", "바이오", "임상", "승인", "신약", "수주잔고", "체결", "공급계약"
]


def generate_dynamic_sector_analysis(sec_name, rate, matched_stocks, news_items):
  """Gemini API 또는 당일 실시간 데이터를 조합하여 매번 새롭게 동적 생성하는 심층 분석기"""
  api_key = os.environ.get("GEMINI_API_KEY")
  stock_summary_text = ", ".join([f"{s['name']}({'+' if s['rate']>0 else ''}{s['rate']:.2f}%)" for s in matched_stocks[:3]])
  news_title = news_items[0]["title"] if news_items else "관련 핵심 특징주 뉴스 집계 중"

  # 1. Gemini AI API 연동 시도
  if api_key:
    prompt = f"""
    당신은 전문 금융 애널리스트입니다. 아래의 당일 마감 데이터를 바탕으로 해당 섹터의 주가 흐름과 시장 의미를 통찰력 있게 1~2문장으로 분석해 주세요. 고정된 문장 틀을 사용하지 말고 당일 데이터를 입체적으로 해석해 주세요. 마크다운이나 불필요한 서식 없이 순수 텍스트만 출력하세요.
    
    - 섹터명: {sec_name}
    - 평균 등락률: {rate:+.2f}%
    - 주요 구성 종목: {stock_summary_text}
    - 당일 핵심 뉴스 헤드라인: {news_title}
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
      res = requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
      if res.status_code == 200:
        data = res.json()
        cand = data.get("candidates", [])
        if cand:
          ai_text = cand[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
          if ai_text:
            return ai_text
    except Exception:
      pass

  # 2. API가 없을 경우: 실시간 데이터를 조합하여 매번 다르게 생성하는 동적 조합 분석기
  top_stock = matched_stocks[0] if matched_stocks else {"name": sec_name, "rate": rate}
  other_stocks = ", ".join([s['name'] for s in matched_stocks[1:3]]) if len(matched_stocks) > 1 else "동종 업계"
  
  if rate >= 2.0:
    return f"당일 {top_stock['name']}({top_stock['rate']:+.2f}%)을 필두로 {other_stocks} 등이 가파른 매수세를 유입시키며 섹터 전반의 급등(+{rate:.2f}%)을 주도했습니다. 특히 '{news_title[:32]}...' 관련 보도가 투자 심리를 강하게 자극했습니다."
  elif rate >= 0.5:
    return f"{top_stock['name']}이(+{top_stock['rate']:.2f}%) 양호한 흐름을 보인 가운데, {other_stocks} 등 주요 종목들이 동반 상승하며 섹터가 +{rate:.2f}% 우상향 곡선을 그렸습니다."
  elif rate > 0.0:
    return f"보합권에서 출발한 후 {top_stock['name']} 등 일부 종목의 선별적 반등에 힘입어 +{rate:.2f}% 강보합 마감했습니다. 수급 유입 강도는 다소 제한적인 모습입니다."
  elif rate == 0.0:
    return f"구성 종목 간 매수와 매도 공방이 팽팽하게 맞서며 {sec_name} 지수는 보합(0.00%) 상태로 정규장을 마쳤습니다."
  elif rate > -1.0:
    return f"{top_stock['name']}({top_stock['rate']:+.2f}%) 등 일부 종목이 방어력을 보였으나, {other_stocks} 등에서 단기 차익 실현 물량이 출회되어 {rate:.2f}% 소폭 조정을 받았습니다."
  else:
    return f"기관 및 외국인의 매물이 집중된 가운데 {top_stock['name']}({top_stock['rate']:+.2f}%)을 비롯한 핵심 종목들이 약세를 면치 못하며 섹터가 {rate:.2f}% 하락했습니다. '{news_title[:32]}...' 등 관련 업황 경계감이 부담으로 작용했습니다."


def get_news_score(title, stock_name):
  for bad in EXCLUDE_NEWS_KEYWORDS:
    if bad in title:
      return -1
  score = 0
  aliases = [stock_name]
  if stock_name == "S-Oil":
    aliases.extend(["에쓰오일", "SOil", "S-OIL"])
  elif "홀딩스" in stock_name:
    aliases.append(stock_name.replace("홀딩스", ""))

  has_stock = any(alias in title for alias in aliases if len(alias) >= 2)
  if has_stock:
    score += 5
  has_biz = any(biz in title for biz in BUSINESS_NEWS_KEYWORDS)
  if has_biz:
    score += 4
  return score if (has_stock or has_biz) else -1


def fetch_real_news(keyword, stock_code=""):
  candidates = []
  if stock_code:
    try:
      url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page=1"
      res = requests.get(url, headers=HEADERS, timeout=6)
      soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
      table = soup.find("table", class_="type5")
      if table:
        for tr in table.find_all("tr"):
          td_title = tr.find("td", class_="title")
          td_info = tr.find("td", class_="info")
          if td_title and td_title.find("a"):
            a_tag = td_title.find("a")
            raw_title = a_tag.text.strip()
            score = get_news_score(raw_title, keyword)
            if score > 0:
              candidates.append({
                  "title": raw_title,
                  "press": td_info.text.strip() if td_info else "증권뉴스",
                  "link": "https://finance.naver.com" + a_tag["href"],
                  "score": score,
              })
              if len(candidates) >= 5:
                break
    except Exception:
      pass

  if len(candidates) < 2:
    try:
      enc_query = urllib.parse.quote(f"{keyword} 특징주", encoding="euc-kr")
      url = f"https://finance.naver.com/news/news_search.naver?q={enc_query}"
      res = requests.get(url, headers=HEADERS, timeout=6)
      soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
      dl_list = soup.find_all("dl", class_="articleList") or soup.find_all("dl")
      for dl in dl_list:
        dt = dl.find("dd", class_="articleSubject") or dl.find("dt")
        if dt and dt.find("a"):
          a_tag = dt.find("a")
          raw_title = a_tag.text.strip()
          score = get_news_score(raw_title, keyword)
          if score > 0:
            summary = dl.find("dd", class_="articleSummary")
            press = summary.find("span", class_="press").text.strip() if summary and summary.find("span", class_="press") else "네이버뉴스"
            candidates.append({
                "title": raw_title,
                "press": press,
                "link": "https://finance.naver.com" + a_tag["href"],
                "score": score,
            })
            if len(candidates) >= 4:
              break
    except Exception:
      pass

  candidates.sort(key=lambda x: x["score"], reverse=True)
  return candidates[:2]


def get_exchange_rate():
  try:
    url = "https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
    if res.status_code == 200:
      data = res.json()
      if data and len(data) > 0:
        item = data[0]
        return {
            "name": "원·달러 환율",
            "code_key": "FX_USDKRW",
            "value": f"{item['basePrice']:,.2f}원",
            "change_val": f"{item['changePrice']:,.2f}",
            "change_rate": round(item.get("changeRate", 0) * 100, 2),
            "is_up": item.get("change") == "RISE",
            "is_down": item.get("change") == "FALL",
        }
  except Exception:
    pass
  return {"name": "원·달러 환율", "code_key": "FX_USDKRW", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}


def get_market_indices():
  targets = [
      ("코스피 (KOSPI)", "KOSPI", "https://m.stock.naver.com/api/index/KOSPI/basic"),
      ("코스닥 (KOSDAQ)", "KOSDAQ", "https://m.stock.naver.com/api/index/KOSDAQ/basic"),
      ("코스피 200", "KPI200", "https://m.stock.naver.com/api/index/KPI200/basic"),
  ]
  results = []
  for name, key, url in targets:
    try:
      res = requests.get(url, headers=HEADERS, timeout=8)
      if res.status_code == 200:
        data = res.json()
        val = data.get("closePrice", "-")
        diff = data.get("compareToPreviousClosePrice", "0")
        try:
          rate = abs(float(data.get("fluctuationsRatio", 0)))
        except Exception:
          rate = 0.0
        cd = str(data.get("compareToPreviousPrice", {}).get("code", "3"))
        results.append({
            "name": name,
            "code_key": key,
            "value": val,
            "change_val": diff,
            "change_rate": rate,
            "is_up": cd in ["1", "2"],
            "is_down": cd in ["4", "5"],
        })
        continue
    except Exception:
      pass
    results.append({"name": name, "code_key": key, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})

  results.append(get_exchange_rate())
  return results


def get_market_stocks():
  stocks = {}
  urls = [
      ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1", "KOSPI"),
      ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=2", "KOSPI"),
      ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=1", "KOSDAQ"),
      ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=2", "KOSDAQ"),
  ]
  for u, market in urls:
    try:
      res = requests.get(u, headers=HEADERS, timeout=8)
      soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
      table = soup.find("table", class_="type_2")
      if table:
        for tr in table.find_all("tr"):
          tds = tr.find_all("td")
          if len(tds) >= 5:
            a_tag = tds[1].find("a")
            if a_tag:
              name = a_tag.text.strip()
              code_match = re.search(r"code=(\d+)", a_tag.get("href", ""))
              try:
                stocks[name] = {
                    "price": tds[2].text.strip(),
                    "rate": float(tds[4].text.strip().replace("%", "").replace(",", "")),
                    "code": code_match.group(1) if code_match else "",
                    "market": market,
                }
              except Exception:
                pass
    except Exception:
      pass
  return stocks


KOSPI200_SECTORS = {
    "화학·에너지": ["LG화학", "S-Oil", "SK이노베이션", "롯데케미칼", "SK가스", "GS", "한국가스공사"],
    "이차전지·배터리": ["LG에너지솔루션", "POSCO홀딩스", "포스코퓨처엠", "삼성SDI", "엘앤에프", "에코프로머티"],
    "조선·중공업": ["HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양", "한화엔진", "HD현대", "HD현대마린엔진", "HD현대마린솔루션"],
    "전기·전자 (반도체/IT)": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "한미반도체"],
    "자동차·운송장비": ["현대차", "기아", "현대모비스"],
    "원전·전력인프라": ["한국전력", "두산에너빌리티", "한전기술", "한전KPS", "효성중공업", "산일전기", "대한전선", "일진전기", "LS ELECTRIC", "HD현대일렉트릭"],
    "방위산업·우주항공": ["한화에어로스페이스", "현대로템", "한국항공우주", "한화시스템", "LIG넥스원"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "유한양행", "한미약품", "SK바이오팜"],
    "금융·지주": ["KB금융", "신한지주", "하나금융지주", "메리츠금융지주", "기업은행", "미래에셋증권", "삼성증권", "우리금융지주"],
    "인터넷·플랫폼": ["NAVER", "카카오", "크래프톤"],
    "건설·시공": ["현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "철강·금속": ["고려아연", "현대제철", "동국제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심"],
}

KOSDAQ150_SECTORS = {
    "제약·바이오": ["알테오젠", "HLB", "삼천당제약", "리가켐바이오", "휴젤", "에스티팜", "HK이노엔", "동국제약", "지투지바이오", "디엔디파마텍", "올릭스"],
    "이차전지·소재": ["에코프로비엠", "에코프로", "엔켐", "대주전자재료", "서진시스템", "나노신소재", "피엔티"],
    "반도체 소부장": ["HPSP", "리노공업", "주성엔지니어링", "이오테크닉스", "솔브레인", "동진쎄미켐", "티씨케이", "ISC", "하나머티리얼즈", "대덕전자", "유진테크", "심텍", "원익IPS", "DB하이텍", "테크윙", "파크시스템스"],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드"],
    "로봇·자동화": ["레인보우로보틱스", "로보티즈", "에스에프에이", "휴림로봇", "로보스타", "에스피지", "하이젠알앤엠", "삼현"],
    "피팅·배관기자재": ["성광벤드", "태광", "하이록코리아"],
}


def calculate_sectors(sector_dict, stock_data):
  results = []
  for sec_name, stock_names in sector_dict.items():
    matched = []
    rates = []
    for sname in stock_names:
      if sname in stock_data:
        item = stock_data[sname]
        matched.append({"name": sname, "rate": item["rate"], "price": item["price"], "code": item.get("code", "")})
        rates.append(item["rate"])
    if matched:
      matched.sort(key=lambda x: abs(x["rate"]), reverse=True)
      top_stock_name = matched[0]["name"]
      top_stock_code = matched[0].get("code", "")
      news_items = fetch_real_news(top_stock_name, top_stock_code)
      avg_r = sum(rates) / len(rates)
      summary_text = generate_dynamic_sector_analysis(sec_name, avg_r, matched, news_items)
      results.append({
          "name": sec_name,
          "rate": round(avg_r, 2),
          "stocks": matched[:3],
          "lead_stock": top_stock_name,
          "summary": summary_text,
          "news": news_items,
      })
  results.sort(key=lambda x: x["rate"], reverse=True)
  top = results[:3]
  bot = results[-3:]
  bot.reverse()
  return top, bot


def generate_market_review(indices, k200_top, k200_bot, k150_top, k150_bot):
  kospi = next((x for x in indices if "코스피" in x["name"]), {})
  kosdaq = next((x for x in indices if "코스닥" in x["name"]), {})
  fx = next((x for x in indices if "환율" in x["name"]), {})

  k_dir = "상승" if kospi.get("is_up") else ("하락" if kospi.get("is_down") else "보합")
  kq_dir = "상승" if kosdaq.get("is_up") else ("하락" if kosdaq.get("is_down") else "보합")

  news_bullets = ""
  for s, icon, label in [(k200_top[0] if k200_top else {}, "🔴", "코스피 주도"), (k150_top[0] if k150_top else {}, "🔴", "코스닥 주도")]:
    if s and s.get("news"):
      first_n = s["news"][0]
      news_bullets += f"""
        <div class="review-item">
            <span class="bullet">{icon}</span>
            <div><b>[{label}: {s['name']} | {s['rate']:+.2f}%]</b> <a href="{first_n['link']}" target="_blank" class="news-link">"{first_n['title']}"</a> <span class="press-badge">{first_n['press']}</span></div>
        </div>
        """

  return f"""
    <div class="review-card">
        <div class="review-header">
            <span class="review-title">📝 정규장 마감 핵심 요약 & 동적 분석</span>
            <span class="review-tag">실시간 데이터 연동</span>
        </div>
        <div class="review-body">
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[시장 동향]</b> 코스피 <b>{kospi.get('value')}</b>({k_dir}), 코스닥 <b>{kosdaq.get('value')}</b>({kq_dir}), 원·달러 환율 <b>{fx.get('value')}</b>을 기록했습니다.</div>
            </div>
            <div class="review-divider"></div>
            {news_bullets}
        </div>
    </div>
    """


def render_html(indices, k200_top, k200_bot, k150_top, k150_bot):
  index_cards = ""
  for idx in indices:
    sign = "▲ +" if idx["is_up"] else ("▼ -" if idx["is_down"] else "― ")
    color_class = "text-up" if idx["is_up"] else ("text-down" if idx["is_down"] else "text-flat")
    badge_bg = "bg-up-light" if idx["is_up"] else ("bg-down-light" if idx["is_down"] else "bg-gray-100")
    rate_text = f"{sign}{abs(idx['change_rate']):.2f}%"
    diff_text = f" ({idx['change_val']})" if idx["change_val"] != "0" else ""

    index_cards += f"""
        <div class="card" data-index-target="{idx['code_key']}">
            <div class="card-title">{idx['name']}</div>
            <div class="card-value" id="val-{idx['code_key']}">{idx['value']}</div>
            <div class="badge {badge_bg} {color_class}" id="badge-{idx['code_key']}">
                {rate_text}{diff_text}
            </div>
        </div>
        """

  def build_sector_list(sectors):
    html = ""
    if not sectors:
      return '<div class="sector-item">데이터를 집계 중입니다.</div>'

    for s in sectors:
      r = s["rate"]
      sign = "▲ +" if r > 0 else ("▼ -" if r < 0 else "― ")
      color_class = "text-up" if r > 0 else ("text-down" if r < 0 else "text-flat")
      rate_display = f"{sign}{abs(r):.2f}%"

      stock_tags = ""
      for st in s.get("stocks", []):
        st_r = st["rate"]
        st_color = "text-up" if st_r > 0 else ("text-down" if st_r < 0 else "text-flat")
        st_sign = "+" if st_r > 0 else ("-" if st_r < 0 else "")
        stock_tags += f"""
            <span class="stock-pill" data-stock-code="{st.get('code', '')}">
                <span class="stock-name">{st['name']}</span> 
                <b class="stock-rate {st_color}">{st_sign}{abs(st_r):.2f}%</b>
                <span class="stock-price">({st['price']}원)</span>
            </span>"""

      summary_text = s.get("summary", "")
      summary_html = f'<div class="sector-summary"><div class="summary-header"><span class="summary-badge">🔍 동적 심층 분석</span></div><div class="summary-body">{summary_text}</div></div>' if summary_text else ""
      news_tags = f'<div class="sector-news">📰 <a href="{s["news"][0]["link"]}" target="_blank" class="news-link">{s["news"][0]["title"]}</a> <span class="press-badge">{s["news"][0]["press"]}</span></div>' if s.get("news") else ""

      html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{rate_display}</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
                {summary_html}
                {news_tags}
            </div>
            """
    return html

  review_section = generate_market_review(indices, k200_top, k200_bot, k150_top, k150_bot)

  template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>실시간 증시 대시보드</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: #f8fafc; color: #1e293b; padding: 16px; max-width: 960px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 18px; }}
        h1 {{ font-size: 1.45rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .status-bar {{ display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 8px; margin-top: 6px; }}
        .timestamp {{ font-size: 0.86rem; font-weight: 600; color: #334155; background: #e2e8f0; padding: 4px 12px; border-radius: 20px; }}
        .live-status {{ font-size: 0.80rem; font-weight: 700; padding: 4px 10px; border-radius: 20px; }}
        .status-live {{ background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; }}
        .status-closed {{ background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}
        .btn-refresh {{ background: #2563eb; color: #fff; border: none; padding: 5px 12px; border-radius: 20px; font-size: 0.82rem; font-weight: 700; cursor: pointer; transition: all 0.2s; }}
        .btn-refresh:hover {{ background: #1d4ed8; }}
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 22px; }}
        .card {{ background: #fff; padding: 16px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.82rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.30rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; transition: color 0.3s; }}
        .badge {{ display: inline-block; font-size: 0.78rem; font-weight: 700; padding: 3px 10px; border-radius: 6px; }}
        .review-card {{ background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; border-left-width: 5px; border-left-color: #2563eb; padding: 18px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
        .review-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 10px; }}
        .review-title {{ font-size: 1.05rem; font-weight: 800; color: #0f172a; }}
        .review-tag {{ font-size: 0.75rem; font-weight: 700; color: #1d4ed8; background: #dbeafe; padding: 3px 8px; border-radius: 6px; }}
        .review-body {{ display: flex; flex-direction: column; gap: 9px; font-size: 0.92rem; line-height: 1.6; color: #334155; }}
        .review-item {{ display: flex; align-items: flex-start; gap: 8px; }}
        .bullet {{ font-size: 0.95rem; line-height: 1.4; }}
        .review-divider {{ height: 1px; background: #e2e8f0; margin: 4px 0; }}
        .news-link {{ color: #0f172a; text-decoration: none; font-weight: 600; }}
        .news-link:hover {{ color: #2563eb; text-decoration: underline; }}
        .press-badge {{ font-size: 0.72rem; color: #64748b; background: #f1f5f9; border: 1px solid #e2e8f0; padding: 2px 6px; border-radius: 4px; margin-left: 4px; font-weight: 500; }}
        .group-title {{ font-size: 1.15rem; font-weight: 800; margin: 26px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #cbd5e1; color: #0f172a; }}
        .section-title {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 16px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .sector-item {{ padding: 16px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-item:last-child {{ border-bottom: none; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .sector-name {{ font-weight: 800; font-size: 1.05rem; color: #0f172a; }}
        .sector-rate {{ font-weight: 800; font-size: 1.0rem; }}
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 9px; font-size: 0.82rem; }}
        .stock-price {{ color: #64748b; font-size: 0.78rem; margin-left: 3px; }}
        .sector-summary {{ font-size: 0.88rem; line-height: 1.65; color: #334155; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 11px 14px; margin-bottom: 8px; border-left: 4px solid #2563eb; }}
        .summary-header {{ margin-bottom: 4px; }}
        .summary-badge {{ font-weight: 800; font-size: 0.82rem; color: #1d4ed8; background: #dbeafe; padding: 2px 7px; border-radius: 4px; display: inline-block; }}
        .summary-body {{ color: #1e293b; }}
        .sector-news {{ font-size: 0.84rem; color: #475569; background: #ffffff; border: 1px dashed #cbd5e1; padding: 7px 10px; border-radius: 6px; }}
        .text-up {{ color: #e11d48 !important; font-weight: 700; }}
        .text-down {{ color: #2563eb !important; font-weight: 700; }}
        .text-flat {{ color: #64748b !important; font-weight: 700; }}
        .bg-up-light {{ background-color: #ffe4e6 !important; }}
        .bg-down-light {{ background-color: #dbeafe !important; }}
        .bg-gray-100 {{ background-color: #f1f5f9 !important; }}
    </style>
</head>
<body>
    <header>
        <h1>📊 실시간 증시 대시보드</h1>
        <div class="status-bar">
            <span class="timestamp" id="live-clock">🕒 시간 계산 중...</span>
            <span class="live-status" id="market-status">동기화 확인 중</span>
            <button class="btn-refresh" id="btn-refresh" onclick="fetchLiveMarketData()">🔄 실시간 새로고침</button>
        </div>
    </header>
    <div class="grid-indices">{index_cards}</div>
    {review_section}
    <div class="group-title">🏢 코스피 200 업종 동향</div>
    <div class="section-title">🔴 코스피 200 상대 강세 업종</div>
    <div class="sector-box">{build_sector_list(k200_top)}</div>
    <div class="section-title">🔵 코스피 200 상대 약세 업종</div>
    <div class="sector-box">{build_sector_list(k200_bot)}</div>
    <div class="group-title">🚀 코스닥 150 업종 동향</div>
    <div class="section-title">🔴 코스닥 150 상대 강세 업종</div>
    <div class="sector-box">{build_sector_list(k150_top)}</div>
    <div class="section-title">🔵 코스닥 150 상대 약세 업종</div>
    <div class="sector-box">{build_sector_list(k150_bot)}</div>
    <script>
        function updateLiveClock() {{
            const now = new Date();
            const timeStr = new Intl.DateTimeFormat('ko-KR', {{ timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }}).format(now);
            document.getElementById('live-clock').textContent = '🕒 ' + timeStr + ' (KST)';
        }}
        setInterval(updateLiveClock, 1000);
        updateLiveClock();
        
        async function fetchWithProxy(targetUrl) {{
            const proxies = [(u) => 'https://corsproxy.io/?url=' + encodeURIComponent(u), (u) => 'https://api.allorigins.win/raw?url=' + encodeURIComponent(u)];
            for (const getProxy of proxies) {{
                try {{
                    const res = await fetch(getProxy(targetUrl), {{ cache: 'no-store' }});
                    if (res.ok) return await res.json();
                }} catch (e) {{}}
            }}
            throw new Error('프록시 실패');
        }}

        async function fetchLiveMarketData() {{
            const btn = document.getElementById('btn-refresh');
            if (btn) {{ btn.textContent = '⏳ 시세 갱신 중...'; btn.disabled = true; }}
            
            ['KOSPI', 'KOSDAQ', 'KPI200'].forEach(async (key) => {{
                try {{
                    const data = await fetchWithProxy('https://m.stock.naver.com/api/index/' + key + '/basic');
                    if (!data) return;
                    const valEl = document.getElementById('val-' + key);
                    const badgeEl = document.getElementById('badge-' + key);
                    if (valEl && badgeEl) {{
                        valEl.textContent = data.closePrice;
                        const rate = Math.abs(parseFloat(data.fluctuationsRatio || 0));
                        const cd = String(data.compareToPreviousPrice?.code || '3');
                        const isUp = (cd === '1' || cd === '2');
                        const isDown = (cd === '4' || cd === '5');
                        badgeEl.className = 'badge ' + (isUp ? 'bg-up-light text-up' : (isDown ? 'bg-down-light text-down' : 'bg-gray-100 text-flat'));
                        badgeEl.textContent = (isUp ? '▲ +' : (isDown ? '▼ -' : '― ')) + rate.toFixed(2) + '% (' + (data.compareToPreviousClosePrice || '0') + ')';
                    }}
                }} catch(e) {{}}
            }});
            
            setTimeout(() => {{
                if (btn) {{ btn.textContent = '🔄 실시간 새로고침'; btn.disabled = false; }}
            }}, 800);
        }}
    </script>
</body>
</html>
"""
  os.makedirs("public", exist_ok=True)
  with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(template)


def send_kakao_alert(indices, k200_top, k150_top):
  rest_api_key = os.environ.get("KAKAO_REST_API_KEY")
  refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")
  if not rest_api_key or not refresh_token:
    return
  try:
    token_data = {"grant_type": "refresh_token", "client_id": rest_api_key, "refresh_token": refresh_token}
    t_res = requests.post("https://kauth.kakao.com/oauth/token", data=token_data, timeout=5).json()
    access_token = t_res.get("access_token")
    if not access_token:
      return
    
    kospi = next((x for x in indices if "코스피" in x["name"]), {})
    kosdaq = next((x for x in indices if "코스닥" in x["name"]), {})
    fx = next((x for x in indices if "환율" in x["name"]), {})
    
    msg_text = f"📊 [마감 리포트]\n\n• 코스피: {kospi.get('value')}\n• 코스닥: {kosdaq.get('value')}\n• 원·달러: {fx.get('value')}\n\n대시보드에서 동적 심층 분석을 확인하세요."
    send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {"template_object": json.dumps({"object_type": "text", "text": msg_text, "link": {"web_url": DASHBOARD_URL, "mobile_web_url": DASHBOARD_URL}, "button_title": "📊 대시보드 바로가기"})}
    requests.post(send_url, headers=headers, data=payload, timeout=5)
  except Exception:
    pass


if __name__ == "__main__":
  indices = get_market_indices()
  stock_data = get_market_stocks()
  k200_top, k200_bot = calculate_sectors(KOSPI200_SECTORS, stock_data)
  k150_top, k150_bot = calculate_sectors(KOSDAQ150_SECTORS, stock_data)

  render_html(indices, k200_top, k200_bot, k150_top, k150_bot)
  send_kakao_alert(indices, k200_top, k150_top)
