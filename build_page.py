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


def get_exchange_rate():
  """원·달러 환율 데이터 수집"""
  try:
    url = "https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
    if res.status_code == 200:
      data = res.json()
      if data and len(data) > 0:
        item = data[0]
        price = f"{item['basePrice']:,.2f}원"
        diff = f"{item['changePrice']:,.2f}"
        rate = round(item.get("changeRate", 0) * 100, 2)
        chg = item.get("change", "EVEN")
        return {
            "name": "원·달러 환율",
            "code_key": "FX_USDKRW",
            "value": price,
            "change_val": diff,
            "change_rate": rate,
            "is_up": chg == "RISE",
            "is_down": chg == "FALL",
        }
  except Exception:
    pass

  try:
    m_url = "https://finance.naver.com/marketindex/"
    res = requests.get(m_url, headers=HEADERS, timeout=8)
    soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
    box = soup.find("div", class_="head_info")
    if box:
      val_text = box.find("span", class_="value").text.strip().replace(",", "")
      price = f"{float(val_text):,.2f}원"
      diff = box.find("span", class_="change").text.strip()
      box_text = box.text
      return {
          "name": "원·달러 환율",
          "code_key": "FX_USDKRW",
          "value": price,
          "change_val": diff,
          "change_rate": 0.0,
          "is_up": ("상승" in box_text) or ("+" in box_text),
          "is_down": ("하락" in box_text) or ("-" in box_text),
      }
  except Exception:
    pass

  return {
      "name": "원·달러 환율",
      "code_key": "FX_USDKRW",
      "value": "-",
      "change_val": "0",
      "change_rate": 0.0,
      "is_up": False,
      "is_down": False,
  }


def get_market_indices():
  """4대 주요 지수(코스피, 코스닥, 코스피200, 환율) 수집"""
  targets = [
      (
          "코스피 (KOSPI)",
          "KOSPI",
          "https://m.stock.naver.com/api/index/KOSPI/basic",
      ),
      (
          "코스닥 (KOSDAQ)",
          "KOSDAQ",
          "https://m.stock.naver.com/api/index/KOSDAQ/basic",
      ),
      (
          "코스피 200",
          "KPI200",
          "https://m.stock.naver.com/api/index/KPI200/basic",
      ),
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

    results.append({
        "name": name,
        "code_key": key,
        "value": "-",
        "change_val": "0",
        "change_rate": 0.0,
        "is_up": False,
        "is_down": False,
    })

  results.append(get_exchange_rate())
  return results


def get_market_stocks():
  """시가총액 상위 종목 체결가, 등락률 및 종목코드 수집"""
  stocks = {}
  urls = [
      (
          "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1",
          "KOSPI",
      ),
      (
          "https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=2",
          "KOSPI",
      ),
      (
          "https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=1",
          "KOSDAQ",
      ),
      (
          "https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=2",
          "KOSDAQ",
      ),
  ]
  for u, market in urls:
    try:
      res = requests.get(u, headers=HEADERS, timeout=8)
      soup = BeautifulSoup(
          res.content.decode("euc-kr", "replace"), "html.parser"
      )
      table = soup.find("table", class_="type_2")
      if table:
        for tr in table.find_all("tr"):
          tds = tr.find_all("td")
          if len(tds) >= 5:
            a_tag = tds[1].find("a")
            if a_tag:
              name = a_tag.text.strip()
              href = a_tag.get("href", "")
              code_match = re.search(r"code=(\d+)", href)
              code = code_match.group(1) if code_match else ""
              price = tds[2].text.strip()
              rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
              try:
                rate_val = float(rate_text)
                stocks[name] = {
                    "price": price,
                    "rate": rate_val,
                    "code": code,
                    "market": market,
                }
              except Exception:
                pass
    except Exception:
      pass
  return stocks


def fetch_real_news(keyword, stock_code=""):
  """네이버 금융 언론사 뉴스 헤드라인 크롤링"""
  news_list = []
  if stock_code:
    try:
      url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page=1"
      res = requests.get(url, headers=HEADERS, timeout=5)
      soup = BeautifulSoup(
          res.content.decode("euc-kr", "replace"), "html.parser"
      )
      table = soup.find("table", class_="type5")
      if table:
        for tr in table.find_all("tr"):
          td_title = tr.find("td", class_="title")
          td_info = tr.find("td", class_="info")
          if td_title and td_title.find("a"):
            a_tag = td_title.find("a")
            news_list.append({
                "title": a_tag.text.strip(),
                "press": td_info.text.strip() if td_info else "증권뉴스",
                "link": "https://finance.naver.com" + a_tag["href"],
            })
            if len(news_list) >= 2:
              return news_list
    except Exception:
      pass

  try:
    enc_query = urllib.parse.quote(keyword, encoding="euc-kr")
    url = f"https://finance.naver.com/news/news_search.naver?q={enc_query}"
    res = requests.get(url, headers=HEADERS, timeout=5)
    soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
    dl_list = soup.find_all("dl", class_="articleList") or soup.find_all("dl")
    for dl in dl_list:
      dt = dl.find("dd", class_="articleSubject") or dl.find("dt")
      if dt and dt.find("a"):
        a_tag = dt.find("a")
        summary = dl.find("dd", class_="articleSummary")
        press = (
            summary.find("span", class_="press").text.strip()
            if summary and summary.find("span", class_="press")
            else "네이버뉴스"
        )
        news_list.append({
            "title": a_tag.text.strip(),
            "press": press,
            "link": "https://finance.naver.com" + a_tag["href"],
        })
        if len(news_list) >= 2:
          return news_list
  except Exception:
    pass

  return news_list


KOSPI200_SECTORS = {
    "화학·에너지": [
        "LG화학",
        "S-Oil",
        "SK이노베이션",
        "롯데케미칼",
        "SK가스",
        "GS",
        "한국가스공사",
    ],
    "이차전지·배터리": [
        "LG에너지솔루션",
        "POSCO홀딩스",
        "포스코퓨처엠",
        "삼성SDI",
        "엘앤에프",
        "에코프로머티",
    ],
    "조선·중공업": [
        "HD현대중공업",
        "한화오션",
        "삼성중공업",
        "HD한국조선해양",
        "한화엔진",
        "HD현대",
        "HD현대마린엔진",
        "HD현대마린솔루션",
    ],
    "전기·전자 (반도체/IT)": [
        "삼성전자",
        "SK하이닉스",
        "삼성전기",
        "LG이노텍",
        "한미반도체",
    ],
    "자동차·운송장비": ["현대차", "기아", "현대모비스"],
    "원전·전력인프라": [
        "한국전력",
        "두산에너빌리티",
        "한전기술",
        "한전KPS",
        "효성중공업",
        "산일전기",
        "대한전선",
        "일진전기",
        "LS ELECTRIC",
        "HD현대일렉트릭",
    ],
    "방위산업·우주항공": [
        "한화에어로스페이스",
        "현대로템",
        "한국항공우주",
        "한화시스템",
        "LIG넥스원",
    ],
    "제약·바이오": [
        "삼성바이오로직스",
        "셀트리온",
        "유한양행",
        "한미약품",
        "SK바이오팜",
    ],
    "금융·지주": [
        "KB금융",
        "신한지주",
        "하나금융지주",
        "메리츠금융지주",
        "기업은행",
        "미래에셋증권",
        "삼성증권",
        "우리금융지주",
    ],
    "인터넷·플랫폼": ["NAVER", "카카오", "크래프톤"],
    "건설·시공": ["현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "철강·금속": ["고려아연", "현대제철", "동국제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심"],
}

KOSDAQ150_SECTORS = {
    "제약·바이오": [
        "알테오젠",
        "HLB",
        "삼천당제약",
        "리가켐바이오",
        "휴젤",
        "에스티팜",
        "HK이노엔",
        "동국제약",
        "지투지바이오",
        "디엔디파마텍",
        "올릭스",
    ],
    "이차전지·소재": [
        "에코프로비엠",
        "에코프로",
        "엔켐",
        "대주전자재료",
        "서진시스템",
        "나노신소재",
        "피엔티",
    ],
    "반도체 소부장": [
        "HPSP",
        "리노공업",
        "주성엔지니어링",
        "이오테크닉스",
        "솔브레인",
        "동진쎄미켐",
        "티씨케이",
        "ISC",
        "하나머티리얼즈",
        "대덕전자",
        "유진테크",
        "심텍",
        "원익IPS",
        "DB하이텍",
        "테크윙",
        "파크시스템스",
    ],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드"],
    "로봇·자동화": [
        "레인보우로보틱스",
        "로보티즈",
        "에스에프에이",
        "휴림로봇",
        "로보스타",
        "에스피지",
        "하이젠알앤엠",
        "삼현",
    ],
    "피팅·배관기자재": ["성광벤드", "태광", "하이록코리아"],
}


def get_active_gemini_model_name(api_key):
  """구글 API 서버에 현재 키로 사용 가능한 최신 모델명을 직접 조회"""
  try:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    res = requests.get(url, timeout=6)
    if res.status_code == 200:
      models_data = res.json().get("models", [])
      active_models = [
          m.get("name")
          for m in models_data
          if "generateContent" in m.get("supportedGenerationMethods", [])
      ]
      print(f"[Gemini AI] 구글 서버에서 감지된 지원 모델 목록: {active_models}")
      # flash 모델 우선 선택
      for name in active_models:
        if "flash" in name.lower():
          return name
      if active_models:
        return active_models[0]
  except Exception as e:
    print(f"[Gemini AI] 모델 조회 예외: {e}")

  # 기본값: AI 스튜디오의 최신 모델 경로
  return "models/gemini-3-flash-preview"


def run_gemini_ai_sector_analysis(target_sectors):
  """구글 Gemini AI가 12개 섹터의 시세를 직접 읽고 애널리스트 분석문을 실시간 작성"""
  api_key = os.environ.get("GEMINI_API_KEY", "").strip()
  if not api_key:
    print(
        "[INFO] GEMINI_API_KEY가 없어 AI 분석을 건너뜁니다 (Secrets를"
        " 확인해주세요)."
    )
    return {}

  model_path = get_active_gemini_model_name(api_key)
  print(f"[Gemini AI] '{model_path}' 모델로 실시간 분석을 요청합니다...")

  sector_lines = []
  for s in target_sectors:
    name = s["name"]
    rate = s["rate"]
    stocks_info = ", ".join(
        [f"{st['name']}({st['rate']:+.2f}%)" for st in s.get("stocks", [])[:3]]
    )
    sector_lines.append(
        f"- {name}: 평균 {rate:+.2f}% [주요종목: {stocks_info}]"
    )

  prompt = (
      """당신은 국내 최정상 증권사의 투자전략 수석 애널리스트입니다.
오늘 장마감 후 국내 증시의 다음 섹터들에 대해, 투자자들에게 실질적인 도움이 되는 '진짜 심층 시황 분석'을 작성해주세요.

[분석 대상 섹터 및 오늘 시세]
"""
      + "\n".join(sector_lines)
      + """

[작성 요구사항]
1. 정형화된 틀('~섹터는 몇%를 기록하며...', '차별화 장세가 확인되었으며')을 절대로 쓰지 마십시오.
2. 각 섹터마다 완전히 다른 문장 구조와 전문 금융 용어로 차별화되게 작성하십시오.
3. 해당 섹터의 본질적인 원인(예: HBM 수요, 방산 수주 파이프라인, 밸류업 주주환원, 국제유가 및 정제마진 스프레드, EV 캐즘 등)을 깊이 있게 짚으며 2문장 내외로 서술하십시오.
4. 반드시 아래 JSON 형식으로만 출력하십시오 (마크다운 코드블록 없이 순수 JSON):
{
  "섹터명1": "분석 코멘트",
  "섹터명2": "분석 코멘트"
}
"""
  )

  url = f"https://generativelanguage.googleapis.com/v1beta/{model_path}:generateContent?key={api_key}"
  payload = {"contents": [{"parts": [{"text": prompt}]}]}

  try:
    res = requests.post(url, json=payload, timeout=20)
    if res.status_code == 200:
      res_json = res.json()
      raw_text = (
          res_json.get("candidates", [{}])[0]
          .get("content", {})
          .get("parts", [{}])[0]
          .get("text", "")
          .strip()
      )

      # JSON 추출
      clean = raw_text
      if "```json" in clean:
        clean = clean.split("```json")[1].split("```")[0].strip()
      elif "```" in clean:
        clean = clean.split("```")[1].split("```")[0].strip()
      elif "{" in clean and "}" in clean:
        clean = clean[clean.find("{") : clean.rfind("}") + 1]

      parsed = json.loads(clean)
      if isinstance(parsed, dict) and len(parsed) > 0:
        print(
            f"[Gemini AI] 대성공! {len(parsed)}개 섹터에 대한 실시간 AI"
            " 분석문이 성공적으로 생성되었습니다."
        )
        return parsed
    else:
      print(f"[Gemini AI] 생성 실패 (HTTP {res.status_code}): {res.text}")
  except Exception as e:
    print(f"[Gemini AI] 통신 에러 발생: {e}")

  return {}


def calculate_sectors(sector_dict, stock_data):
  results = []
  for sec_name, stock_names in sector_dict.items():
    matched = []
    rates = []
    for sname in stock_names:
      if sname in stock_data:
        item = stock_data[sname]
        matched.append({
            "name": sname,
            "rate": item["rate"],
            "price": item["price"],
            "code": item.get("code", ""),
        })
        rates.append(item["rate"])
    if matched:
      matched.sort(key=lambda x: abs(x["rate"]), reverse=True)
      top_stock_name = matched[0]["name"]
      top_stock_code = matched[0].get("code", "")
      news_items = fetch_real_news(top_stock_name, top_stock_code)
      avg_r = sum(rates) / len(rates)
      results.append({
          "name": sec_name,
          "rate": round(avg_r, 2),
          "stocks": matched[:3],
          "lead_stock": top_stock_name,
          "news": news_items,
          "summary": "",
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

  k_dir = (
      "상승"
      if kospi.get("is_up")
      else ("하락" if kospi.get("is_down") else "보합")
  )
  kq_dir = (
      "상승"
      if kosdaq.get("is_up")
      else ("하락" if kosdaq.get("is_down") else "보합")
  )

  fx_text = ""
  if fx.get("is_down"):
    fx_text = (
        f"원·달러 환율이 <b>{fx.get('value')}</b>로 하향 안정화되며 수급 여건을"
        " 지지했습니다."
    )
  elif fx.get("is_up"):
    fx_text = (
        f"원·달러 환율이 <b>{fx.get('value')}</b>로 상승세를 보이며 대형"
        " 수출주에 영향을 미쳤습니다."
    )
  else:
    fx_text = (
        f"원·달러 환율은 <b>{fx.get('value')}</b> 선에서 보합권 흐름을"
        " 나타냈습니다."
    )

  target_sectors = []
  if k200_top:
    s = k200_top[0]
    icon = "🔴" if s["rate"] > 0 else "🔵"
    lbl = (
        "코스피 상승 주도" if s["rate"] > 0 else "코스피 상대 강세 (최소 낙폭)"
    )
    target_sectors.append((s, icon, lbl))

  if k150_top:
    s = k150_top[0]
    icon = "🔴" if s["rate"] > 0 else "🔵"
    lbl = (
        "코스닥 상승 주도" if s["rate"] > 0 else "코스닥 상대 강세 (최소 낙폭)"
    )
    target_sectors.append((s, icon, lbl))

  if k200_bot:
    s = k200_bot[0]
    target_sectors.append((s, "🔵", "코스피 낙폭 과대 섹터"))

  news_bullets = ""
  for s, icon, label in target_sectors:
    n_text = ""
    if s.get("news"):
      first_n = s["news"][0]
      n_text = (
          f'<a href="{first_n["link"]}" target="_blank"'
          f' class="news-link">"{first_n["title"]}"</a> <span'
          f' class="press-badge">{first_n["press"]}</span>'
      )
    else:
      n_text = f"{s['lead_stock']} 등 주력 종목 중심 수급 공방"

    rate_sign = "+" if s["rate"] > 0 else "-"
    news_bullets += f"""
        <div class="review-item">
            <span class="bullet">{icon}</span>
            <div><b>[{label}: {s['name']} | {rate_sign}{abs(s['rate']):.2f}%]</b> {n_text.replace("포토", "").replace("종합", "").strip()}</div>
        </div>
        """

  review_html = f"""
    <div class="review-card">
        <div class="review-header">
            <span class="review-title">📝 정규장 핵심 마감 총평 & 주요 이슈</span>
            <span class="review-tag">공식 언론사 속보</span>
        </div>
        <div class="review-body">
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[시장 동향]</b> 코스피 <b>{kospi.get('value')}</b>({k_dir}), 코스닥 <b>{kosdaq.get('value')}</b>({kq_dir})을 기록했습니다.</div>
            </div>
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[환율 흐름]</b> {fx_text}</div>
            </div>
            <div class="review-divider"></div>
            <div style="font-weight: 700; color: #1e293b; margin-bottom: 4px;">📰 당일 주요 섹터별 언론사 보도 헤드라인</div>
            {news_bullets}
        </div>
    </div>
    """
  return review_html


def render_html(indices, k200_top, k200_bot, k150_top, k150_bot):
  index_cards = ""
  for idx in indices:
    if idx["is_up"]:
      sign = "▲ +"
      color_class = "text-up"
      badge_bg = "bg-up-light"
    elif idx["is_down"]:
      sign = "▼ -"
      color_class = "text-down"
      badge_bg = "bg-down-light"
    else:
      sign = "― "
      color_class = "text-flat"
      badge_bg = "bg-gray-100"

    rate_text = (
        f"{sign}{abs(idx['change_rate']):.2f}%"
        if idx["change_rate"] != 0.0
        else f"{sign}0.00%"
    )
    diff_text = f" ({idx['change_val']})" if idx["change_val"] != "0" else ""

    index_cards += f"""
        <div class="card" data-index-target="{idx['code_key']}">
            <div class="card-title">{idx['name']}</div>
            <div class="card-value">{idx['value']}</div>
            <div class="badge {badge_bg} {color_class}">
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
      if r > 0:
        sign = "▲ +"
        color_class = "text-up"
      elif r < 0:
        sign = "▼ -"
        color_class = "text-down"
      else:
        sign = "― "
        color_class = "text-flat"

      rate_display = f"{sign}{abs(r):.2f}%"

      stock_tags = ""
      for st in s.get("stocks", []):
        st_r = st["rate"]
        st_color = (
            "text-up"
            if st_r > 0
            else ("text-down" if st_r < 0 else "text-flat")
        )
        st_sign = "+" if st_r > 0 else ("-" if st_r < 0 else "")
        code_attr = (
            f'data-stock-code="{st.get("code", "")}"' if st.get("code") else ""
        )
        stock_tags += f"""
            <span class="stock-pill" {code_attr}>
                <span class="stock-name">{st['name']}</span> 
                <b class="stock-rate {st_color}">{st_sign}{abs(st_r):.2f}%</b>
                <span class="stock-price">({st['price']}원)</span>
            </span>"""

      news_tags = ""
      if s.get("news"):
        for n in s["news"][:1]:
          news_tags += f"""<div class="sector-news">📰 <a href="{n['link']}" target="_blank" class="news-link">{n['title']}</a> <span class="press-badge">{n['press']}</span></div>"""
      else:
        news_tags = """<div class="sector-news" style="color: #94a3b8;">당일 집계된 관련 특징주 뉴스가 없습니다.</div>"""

      summary_text = s.get("summary", "").strip()
      if summary_text:
        summary_tag = (
            f"""<div class="sector-summary">🤖 <b>Gemini AI 실시간 시황"""
            f""" 분석:</b> {summary_text}</div>"""
        )
      else:
        summary_tag = ""

      html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{rate_display}</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
                {news_tags}
                {summary_tag}
            </div>
            """
    return html

  review_section = generate_market_review(
      indices, k200_top, k200_bot, k150_top, k150_bot
  )

  kst_now = datetime.now(timezone(timedelta(hours=9)))
  build_time_str = kst_now.strftime("%Y년 %m월 %d일 %H:%M:%S")

  template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>실시간 국내 증시 대시보드</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: #f8fafc; color: #1e293b; padding: 16px; max-width: 960px; margin: 0 auto; }}
        
        header {{ text-align: center; margin-bottom: 18px; }}
        h1 {{ font-size: 1.45rem; font-weight: 800; color: #0f172a; margin-bottom: 8px; }}
        
        .status-bar {{ display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 8px; margin-top: 6px; }}
        .timestamp {{ font-size: 0.86rem; font-weight: 600; color: #1e293b; background: #e2e8f0; padding: 5px 14px; border-radius: 20px; }}
        .live-status {{ font-size: 0.80rem; font-weight: 700; padding: 5px 12px; border-radius: 20px; }}
        .status-live {{ background-color: #fee2e2; color: #dc2626; border: 1px solid #fca5a5; }}
        .status-closed {{ background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}
        .btn-refresh {{ background: #2563eb; color: #fff; border: none; padding: 6px 14px; border-radius: 20px; font-size: 0.84rem; font-weight: 700; cursor: pointer; transition: all 0.2s; }}
        .btn-refresh:hover {{ background: #1d4ed8; }}
        
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 22px; }}
        .card {{ background: #fff; padding: 16px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.82rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.30rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
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
        .sector-item {{ padding: 14px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-item:last-child {{ border-bottom: none; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .sector-name {{ font-weight: 700; font-size: 0.98rem; }}
        .sector-rate {{ font-weight: 800; font-size: 0.98rem; }}
        
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 9px; font-size: 0.82rem; }}
        .stock-price {{ color: #64748b; font-size: 0.78rem; margin-left: 3px; }}
        .sector-news {{ font-size: 0.84rem; color: #475569; background: #f8fafc; padding: 7px 10px; border-radius: 6px; border-left: 3px solid #3b82f6; margin-bottom: 6px; }}
        
        .sector-summary {{ font-size: 0.84rem; line-height: 1.65; color: #1e293b; background: #f0fdf4; border-radius: 6px; padding: 10px 14px; border: 1px solid #bbf7d0; border-left-width: 4px; border-left-color: #16a34a; }}
        .sector-summary b {{ color: #15803d; }}

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
        <h1>📊 국내 증시 자동 갱신 대시보드</h1>
        <div class="status-bar">
            <span class="timestamp">🕒 최신 데이터 수집 시각: <b>{build_time_str}</b> (KST)</span>
            <span class="live-status" id="market-status">장 상태 확인 중</span>
            <button class="btn-refresh" onclick="forceReload()">🔄 페이지 새로고침</button>
        </div>
    </header>

    <div class="grid-indices">
        {index_cards}
    </div>

    {review_section}

    <div class="group-title">🏢 코스피 200 업종 동향</div>
    <div class="section-title">🔴 코스피 200 상대 강세 업종 (등락률 상위)</div>
    <div class="sector-box">
        {build_sector_list(k200_top)}
    </div>
    <div class="section-title">🔵 코스피 200 상대 약세 업종 (등락률 하위)</div>
    <div class="sector-box">
        {build_sector_list(k200_bot)}
    </div>

    <div class="group-title">🚀 코스닥 150 업종 동향</div>
    <div class="section-title">🔴 코스닥 150 상대 강세 업종 (등락률 상위)</div>
    <div class="sector-box">
        {build_sector_list(k150_top)}
    </div>
    <div class="section-title">🔵 코스닥 150 상대 약세 업종 (등락률 하위)</div>
    <div class="sector-box">
        {build_sector_list(k150_bot)}
    </div>

    <script>
        function forceReload() {{
            window.location.href = window.location.pathname + '?_t=' + Date.now();
        }}

        (function checkMarket() {{
            const now = new Date();
            const kstDate = new Date(now.toLocaleString("en-US", {{ timeZone: "Asia/Seoul" }}));
            const day = kstDate.getDay();
            const hour = kstDate.getHours();
            const min = kstDate.getMinutes();
            const timeVal = hour * 60 + min;
            const isWeekday = (day >= 1 && day <= 5);
            const isMarketOpen = isWeekday && (timeVal >= 540 && timeVal < 930);

            const statusEl = document.getElementById('market-status');
            if (statusEl) {{
                if (isMarketOpen) {{
                    statusEl.className = 'live-status status-live';
                    statusEl.textContent = '🔴 장중 15분 주기 자동 갱신 중';
                }} else {{
                    statusEl.className = 'live-status status-closed';
                    statusEl.textContent = '🏁 15:30 정규장 마감 완료';
                }}
            }}
        }})();
    </script>
</body>
</html>
"""
  os.makedirs("public", exist_ok=True)
  with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(template)


def send_kakao_alert(indices, k200_top, k150_top):
  """카카오톡 알림 제어"""
  github_event = os.environ.get("GITHUB_EVENT_NAME", "")
  kst_now = datetime.now(timezone(timedelta(hours=9)))

  is_manual = github_event == "workflow_dispatch"
  is_market_close_time = (kst_now.hour == 16) or (
      kst_now.hour == 15 and kst_now.minute >= 30
  )

  if not is_manual and not is_market_close_time:
    print(
        f"[INFO] 현재 시각 {kst_now.strftime('%H:%M')} KST - 장중 자동 갱신 완료"
        " (카톡 알림은 16:00 마감 시에만 1회 발송됩니다)."
    )
    return

  rest_api_key = os.environ.get("KAKAO_REST_API_KEY")
  refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN")

  if not rest_api_key or not refresh_token:
    print("[INFO] 카카오 환경변수가 설정되지 않아 발송을 건너뜁니다.")
    return

  try:
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    t_res = requests.post(token_url, data=token_data, timeout=5).json()
    access_token = t_res.get("access_token")

    if not access_token:
      print(f"[ERROR] 토큰 갱신 실패: {t_res}")
      return

    date_str = (
        kst_now.strftime("%m/%d 15:30 마감")
        if is_market_close_time
        else kst_now.strftime("%m/%d %H:%M 기준")
    )

    kospi = next((x for x in indices if "코스피" in x["name"]), {})
    kosdaq = next((x for x in indices if "코스닥" in x["name"]), {})
    fx = next((x for x in indices if "환율" in x["name"]), {})

    k_sign = (
        "▲ +"
        if kospi.get("is_up")
        else ("▼ -" if kospi.get("is_down") else "")
    )
    kq_sign = (
        "▲ +"
        if kosdaq.get("is_up")
        else ("▼ -" if kosdaq.get("is_down") else "")
    )
    fx_sign = (
        "▲ +" if fx.get("is_up") else ("▼ -" if fx.get("is_down") else "")
    )

    k200_lead = k200_top[0]["name"] if k200_top else "집계중"
    k150_lead = k150_top[0]["name"] if k150_top else "집계중"

    msg_text = f"""📊 [정규장 마감 리포트] {date_str}

• 코스피: {kospi.get('value')} ({k_sign}{abs(kospi.get('change_rate', 0)):.2f}%, {kospi.get('change_val')})
• 코스닥: {kosdaq.get('value')} ({kq_sign}{abs(kosdaq.get('change_rate', 0)):.2f}%, {kosdaq.get('change_val')})
• 원·달러: {fx.get('value')} ({fx_sign}{abs(fx.get('change_rate', 0)):.2f}%)
• 상대강세: {k200_lead} / {k150_lead}

상세 업종 동향과 뉴스는 아래 버튼을 눌러 확인하세요."""

    send_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": msg_text,
            "link": {
                "web_url": DASHBOARD_URL,
                "mobile_web_url": DASHBOARD_URL,
            },
            "button_title": "📊 증시 대시보드 바로가기",
        })
    }
    s_res = requests.post(send_url, headers=headers, data=payload, timeout=5)
    if s_res.status_code == 200:
      print("[SUCCESS] 카카오톡 발송 완료")
    else:
      print(f"[ERROR] 카카오톡 발송 실패: {s_res.text}")

  except Exception as e:
    print(f"[ERROR] 전송 중 오류: {e}")


if __name__ == "__main__":
  indices = get_market_indices()
  stock_data = get_market_stocks()
  k200_top, k200_bot = calculate_sectors(KOSPI200_SECTORS, stock_data)
  k150_top, k150_bot = calculate_sectors(KOSDAQ150_SECTORS, stock_data)

  # 화면에 노출될 12개 섹터를 수집하여 Gemini AI로 실시간 분석 수행
  all_display_sectors = k200_top + k200_bot + k150_top + k150_bot
  ai_analysis_map = run_gemini_ai_sector_analysis(all_display_sectors)

  # Gemini AI가 작성한 분석문만 정확히 매핑
  for s in all_display_sectors:
    s["summary"] = ai_analysis_map.get(s["name"], "")

  render_html(indices, k200_top, k200_bot, k150_top, k150_bot)
  send_kakao_alert(indices, k200_top, k150_top)
