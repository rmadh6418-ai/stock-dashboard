import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def get_market_indices():
    """주요 지수, VKOSPI, 환율 수집"""
    targets = {
        "코스피 (KOSPI)": "KOSPI",
        "코스닥 (KOSDAQ)": "KOSDAQ",
        "코스피 200": "KPI200",
        "코스닥 150": "KCQ150",
        "VKOSPI (변동성)": "V-KOSPI200"
    }
    result = []
    for name, code in targets.items():
        url = f"https://m.stock.naver.com/api/index/{code}/basic"
        res = requests.get(url, headers=HEADERS).json()
        now_val = res.get("nowValue", "-")
        change_rate = float(res.get("changeRate", "0"))
        change_val = res.get("changeValue", "0")
        
        is_up = change_rate > 0
        is_down = change_rate < 0
        result.append({
            "name": name,
            "value": now_val,
            "change_val": change_val,
            "change_rate": change_rate,
            "is_up": is_up,
            "is_down": is_down
        })
        
    # 원·달러 환율
    fx_url = "https://m.stock.naver.com/api/exchange/FX_USDKRW/basic"
    fx_res = requests.get(fx_url, headers=HEADERS).json()
    fx_rate = float(fx_res.get("changeRate", "0"))
    result.append({
        "name": "원·달러 환율",
        "value": f"{fx_res.get('nowValue', '-')}원",
        "change_val": fx_res.get("changeValue", "0"),
        "change_rate": fx_rate,
        "is_up": fx_rate > 0,
        "is_down": fx_rate < 0
    })
    return result

def get_sector_data():
    """상위/하위 업종 및 대표 종목 수집"""
    url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")
    rows = soup.find("table", class_="type_1").find_all("tr")

    sectors = []
    for r in rows:
        cols = r.find_all("td")
        if len(cols) >= 2 and cols[0].find("a"):
            name = cols[0].find("a").text.strip()
            rate_str = cols[1].text.strip().replace("%", "")
            link = "https://finance.naver.com" + cols[0].find("a")["href"]
            try:
                sectors.append({"name": name, "rate": float(rate_str), "link": link})
            except:
                continue

    sectors.sort(key=lambda x: x["rate"], reverse=True)
    top_3 = sectors[:3]
    bot_3 = sectors[-3:]
    bot_3.reverse()

    def fetch_stocks(sector_url):
        s_res = requests.get(sector_url, headers=HEADERS)
        s_soup = BeautifulSoup(s_res.content.decode("euc-kr", "replace"), "html.parser")
        s_table = s_soup.find("table", class_="type_5")
        stocks = []
        if s_table:
            for r in s_table.find_all("tr")[2:]:
                tds = r.find_all("td")
                if len(tds) >= 4 and tds[0].text.strip():
                    s_name = tds[0].text.strip()
                    s_rate = tds[3].text.strip().replace("%", "")
                    try:
                        rate_val = float(s_rate)
                        stocks.append({"name": s_name, "rate": rate_val})
                    except:
                        pass
                    if len(stocks) == 3:
                        break
        return stocks

    for s in top_3:
        s["stocks"] = fetch_stocks(s["link"])
    for s in bot_3:
        s["stocks"] = fetch_stocks(s["link"])

    return top_3, bot_3

def render_html(indices, top_sec, bot_sec):
    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 마감 기준")
    
    # 지수 카드 생성
    index_cards = ""
    for idx in indices:
        color_class = "text-up" if idx["is_up"] else ("text-down" if idx["is_down"] else "text-flat")
        sign = "🔺 +" if idx["is_up"] else ("🔻 -" if idx["is_down"] else "➖ ")
        badge_bg = "bg-up-light" if idx["is_up"] else ("bg-down-light" if idx["is_down"] else "bg-gray-100")
        
        index_cards += f"""
        <div class="card">
            <div class="card-title">{idx['name']}</div>
            <div class="card-value">{idx['value']}</div>
            <div class="badge {badge_bg} {color_class}">
                {sign}{abs(idx['change_rate']):.2f}% ({idx['change_val']})
            </div>
        </div>
        """

    # 섹터 리스트 생성 함수
    def build_sector_list(sectors, is_up=True):
        html = ""
        sign = "🔺 +" if is_up else "🔻 "
        color_class = "text-up" if is_up else "text-down"
        for s in sectors:
            stock_tags = ""
            for st in s.get("stocks", []):
                st_color = "text-up" if st["rate"] > 0 else ("text-down" if st["rate"] < 0 else "text-flat")
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
    <title>국내 증시 마감 요약 대시보드</title>
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
        
        .section-title {{ font-size: 1.05rem; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 6px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 14px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .sector-item {{ padding: 10px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-item:last-child {{ border-bottom: none; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .sector-name {{ font-weight: 600; font-size: 0.95rem; }}
        .sector-rate {{ font-weight: 700; font-size: 0.95rem; }}
        
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 3px 8px; font-size: 0.8rem; }}
        
        .text-up {{ color: #e11d48; }} /* 상승 빨간색 */
        .text-down {{ color: #2563eb; }} /* 하락 파란색 */
        .text-flat {{ color: #64748b; }}
        .bg-up-light {{ background-color: #ffe4e6; }}
        .bg-down-light {{ background-color: #dbeafe; }}
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
