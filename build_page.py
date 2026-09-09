from datetime import datetime
import os
import re
from bs4 import BeautifulSoup
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}


def fetch_index_item(name, code):
  """1차 API 조회 실패 시 2차 HTML 파싱으로 100% 수집"""
  # 1차 시도: api.stock.naver.com
  api_urls = [
      f"https://api.stock.naver.com/index/{code}/basic",
      f"https://api.stock.naver.com/index/{code.replace('-', '')}/basic",
  ]
  for url in api_urls:
    try:
      res = requests.get(
          url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=5
      )
      if res.status_code == 200:
        data = res.json()
        price = data.get("closePrice") or data.get("nowValue")
        rate = data.get("fluctuationsRatio") or data.get("changeRate")
        diff = data.get("compareToPreviousClosePrice") or data.get(
            "changeValue"
        )
        trend = data.get("compareToPreviousPrice", {})
        trend_name = trend.get("name", "") if isinstance(trend, dict) else ""

        if price:
          rate_val = float(str(rate).replace("%", "").replace(",", ""))
          is_up = rate_val > 0 or "RISING" in trend_name or "UP" in trend_name
          is_down = (
              rate_val < 0 or "FALLING" in trend_name or "DOWN" in trend_name
          )
          return {
              "name": name,
              "value": str(price),
              "change_val": str(diff).replace("+", "").replace("-", ""),
              "change_rate": abs(rate_val),
              "is_up": is_up,
              "is_down": is_down,
          }
    except Exception:
      pass

  # 2차 시도: finance.naver.com HTML 파싱
  try:
    h_url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
    res = requests.get(h_url, headers=HEADERS, timeout=5)
    soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
    now_elem = soup.find(id="now_value")
    if now_elem:
      price = now_elem.text.strip()
      change_span = soup.find(id="change_value_and_rate")
      diff = "0"
      rate_val = 0.0
      is_up = False
      is_down = False
      if change_span:
        text = change_span.text.strip().split()
        if len(text) >= 2:
          diff = text[0].replace("+", "").replace("-", "")
          rate_val = abs(
              float(text[1].replace("%", "").replace("+", "").replace("-", ""))
          )
          if "+" in text[0] or "+" in text[1]:
            is_up = True
          elif "-" in text[0] or "-" in text[1]:
            is_down = True
      return {
          "name": name,
          "value": price,
          "change_val": diff,
          "change_rate": rate_val,
          "is_up": is_up,
          "is_down": is_down,
      }
  except Exception:
    pass

  return {
      "name": name,
      "value": "-",
      "change_val": "0",
      "change_rate": 0.0,
      "is_up": False,
      "is_down": False,
  }


def fetch_usd_krw():
  """원·달러 환율 수집"""
  try:
    url = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW"
    res = requests.get(
        url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=5
    )
    if res.status_code == 200:
      data = res.json()
      price = data.get("closePrice") or data.get("nowValue")
      rate = float(str(data.get("fluctuationsRatio", "0")).replace("%", ""))
      diff = data.get("compareToPreviousClosePrice") or data.get("changeValue")
      if price:
        return {
            "name": "원·달러 환율",
            "value": f"{price}원",
            "change_val": str(diff).replace("+", "").replace("-", ""),
            "change_rate": abs(rate),
            "is_up": rate > 0,
            "is_down": rate < 0,
        }
  except Exception:
    pass

  try:
    res = requests.get(
        "https://finance.naver.com/marketindex/", headers=HEADERS, timeout=5
    )
    soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
    box = soup.find("div", class_="head_info")
    if box:
      price = box.find("span", class_="value").text.strip()
      diff = box.find("span", class_="change").text.strip()
      blind = box.find("span", class_="blind").text.strip()
      return {
          "name": "원·달러 환율",
          "value": f"{price}원",
          "change_val": diff,
          "change_rate": 0.0,
          "is_up": "상승" in blind,
          "is_down": "하락" in blind,
      }
  except Exception:
    pass

  return {
      "name": "원·달러 환율",
      "value": "-",
      "change_val": "0",
      "change_rate": 0.0,
      "is_up": False,
      "is_down": False,
  }


def get_market_indices():
  targets = [
      ("코스피 (KOSPI)", "KOSPI"),
      ("코스닥 (KOSDAQ)", "KOSDAQ"),
      ("코스피 200", "KPI200"),
      ("코스닥 150", "KCQ150"),
      ("VKOSPI (변동성)", "V-KOSPI200"),
  ]
  indices = [fetch_index_item(name, code) for name, code in targets]
  indices.append(fetch_usd_krw())
  return indices


def get_sector_data():
  url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
  sectors = []
  try:
    res = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
    rows = soup.find("table", class_="type_1").find_all("tr")

    for r in rows:
      cols = r.find_all("td")
      if len(cols) >= 2 and cols[0].find("a"):
        name = cols[0].find("a").text.strip()
        rate_str = cols[1].text.strip().replace("%", "")
        link = "https://finance.naver.com" + cols[0].find("a")["href"]
        try:
          sectors.append({"name": name, "rate": float(rate_str), "link": link})
        except Exception:
          continue
  except Exception:
    pass

  sectors.sort(key=lambda x: x["rate"], reverse=True)
  top_3 = sectors[:3] if len(sectors) >= 3 else sectors
  bot_3 = sectors[-3:] if len(sectors) >= 3 else []
  bot_3.reverse()

  def fetch_stocks(sector_url):
    stocks = []
    try:
      s_res = requests.get(sector_url, headers=HEADERS, timeout=10)
      s_soup = BeautifulSoup(
          s_res.content.decode("euc-kr", "replace"), "html.parser"
      )
      s_table = s_soup.find("table", class_="type_5")
      if s_table:
        for r in s_table.find_all("tr")[2:]:
          tds = r.find_all("td")
          if len(tds) >= 4 and tds[0].text.strip():
            name = tds[0].text.strip()
            rate = tds[3].text.strip().replace("%", "")
            try:
              rate_val = float(rate)
              stocks.append({"name": name, "rate": rate_val})
            except Exception:
              pass
            if len(stocks) == 3:
              break
    except Exception:
      pass
    return stocks

  for s in top_3:
    s["stocks"] = fetch_stocks(s["link"])
  for s in bot_3:
    s["stocks"] = fetch_stocks(s["link"])

  return top_3, bot_3


def render_html(indices, top_sec, bot_sec):
  now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 마감 기준")

  index_cards = ""
  for idx in indices:
    color_class = (
        "text-up"
        if idx["is_up"]
        else ("text-down" if idx["is_down"] else "text-flat")
    )
    sign = (
        "🔺 +"
        if idx["is_up"]
        else ("🔻 -" if idx["is_down"] else "➖ ")
    )
    badge_bg = (
        "bg-up-light"
        if idx["is_up"]
        else ("bg-down-light" if idx["is_down"] else "bg-gray-100")
    )

    rate_text = (
        f"{sign}{idx['change_rate']:.2f}%"
        if idx["change_rate"] > 0
        else (
            "🔺 상승"
            if idx["is_up"]
            else ("🔻 하락" if idx["is_down"] else "➖ 보합")
        )
    )
    diff_text = f" ({idx['change_val']})" if idx["change_val"] != "0" else ""

    index_cards += f"""
        <div class="card">
            <div class="card-title">{idx['name']}</div>
            <div class="card-value">{idx['value']}</div>
            <div class="badge {badge_bg} {color_class}">
                {rate_text}{diff_text}
            </div>
        </div>
        """

  def build_sector_list(sectors, is_up=True):
    html = ""
    sign = "🔺 +" if is_up else "🔻 "
    color_class = "text-up" if is_up else "text-down"
    if not sectors:
      return '<div class="sector-item">데이터를 집계 중입니다.</div>'

    for s in sectors:
      stock_tags = ""
      for st in s.get("stocks", []):
        st_color = (
            "text-up"
            if st["rate"] > 0
            else ("text-down" if st["rate"] < 0 else "text-flat")
        )
        st_sign = "+" if st["rate"] > 0 else ""
        stock_tags += f'<span class="stock-pill">{st["name"]} <b class="{st_color}">{st_sign}{st["rate"]}%</b></span>'

      html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{sign}{s['rate']}%</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
            </div>
            """
    return html

  top_html = build_sector_list(top_sec, is_up=True)
  bot_html = build_sector_list(bot_sec, is_up=False)

  template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>국내 정규장 마감 대시보드</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: #f4f6f9; color: #1e293b; padding: 16px; max-width: 900px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 20px; }}
        h1 {{ font-size: 1.4rem; font-weight: 700; color: #0f172a; margin-bottom: 4px; }}
        .timestamp {{ font-size: 0.85rem; color: #64748b; }}
        
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 24px; }}
        .card {{ background: #fff; padding: 14px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.8rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.15rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .badge {{ display: inline-block; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; }}
        
        .section-title {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 12px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 14px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .sector-item {{ padding: 10px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-item:last-child {{ border-bottom: none; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .sector-name {{ font-weight: 600; font-size: 0.95rem; }}
        .sector-rate {{ font-weight: 700; font-size: 0.95rem; }}
        
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 3px 8px; font-size: 0.8rem; }}
        
        .text-up {{ color: #e11d48; }}
        .text-down {{ color: #2563eb; }}
        .text-flat {{ color: #64748b; }}
        .bg-up-light {{ background-color: #ffe4e6; }}
        .bg-down-light {{ background-color: #dbeafe; }}
        .bg-gray-100 {{ background-color: #f1f5f9; }}
    </style>
</head>
<body>
    <header>
        <h1>📊 국내 정규장 마감 대시보드</h1>
        <div class="timestamp">{now_str}</div>
    </header>

    <div class="grid-indices">
        {index_cards}
    </div>

    <div class="section-title">🔴 등락률 상위 업종</div>
    <div class="sector-box">
        {top_html}
    </div>

    <div class="section-title">🔵 등락률 하위 업종</div>
    <div class="sector-box">
        {bot_html}
    </div>
</body>
</html>
"""
  os.makedirs("public", exist_ok=True)
  with open("public/index.html", "w", encoding="utf-8") as f:
    f.write(template)


if __name__ == "__main__":
  indices = get_market_indices()
  top_sec, bot_sec = get_sector_data()
  render_html(indices, top_sec, bot_sec)
