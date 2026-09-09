import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# PC 웹 페이지용 헤더
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/"
}

# 모바일 API 전용 헤더
MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    "Referer": "https://m.stock.naver.com/",
    "Origin": "https://m.stock.naver.com"
}

def parse_change_text(text):
    """'상승 12.34 +0.40%' 또는 '하락 5.20 -0.71%' 형태에서 등락폭, 등락률, 부호 안전 추출"""
    is_up = ("상승" in text) or ("+" in text)
    is_down = ("하락" in text) or ("-" in text)
    
    # 숫자 및 소수점만 추출
    nums = re.findall(r'[\d\.,]+', text)
    diff = nums[0] if len(nums) >= 1 else "0"
    rate = 0.0
    if len(nums) >= 2:
        try:
            rate = abs(float(nums[1].replace(',', '')))
        except:
            rate = 0.0
            
    return diff, rate, is_up, is_down

def get_market_indices():
    results = []

    # 1. 코스피, 코스닥, 코스피 200 (네이버 증시 메인에서 일괄 추출)
    main_url = "https://finance.naver.com/sise/"
    try:
        res = requests.get(main_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        
        targets = [
            ("코스피 (KOSPI)", "KOSPI"),
            ("코스닥 (KOSDAQ)", "KOSDAQ"),
            ("코스피 200", "KPI200")
        ]
        
        for name, prefix in targets:
            now_elem = soup.find(id=f"{prefix}_now")
            change_elem = soup.find(id=f"{prefix}_change")
            if now_elem:
                price = now_elem.text.strip()
                c_text = change_elem.text.strip() if change_elem else ""
                diff, rate, is_up, is_down = parse_change_text(c_text)
                results.append({
                    "name": name,
                    "value": price,
                    "change_val": diff,
                    "change_rate": rate,
                    "is_up": is_up,
                    "is_down": is_down
                })
            else:
                results.append({"name": name, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})
    except:
        for name in ["코스피 (KOSPI)", "코스닥 (KOSDAQ)", "코스피 200"]:
            results.append({"name": name, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})

    # 2. 코스닥 150 (KQ150)
    kq_val, kq_diff, kq_rate, kq_up, kq_down = "-", "0", 0.0, False, False
    try:
        kq_url = "https://finance.naver.com/sise/sise_index.naver?code=KQ150"
        res = requests.get(kq_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        now_elem = soup.find(id="now_value")
        if now_elem:
            kq_val = now_elem.text.strip()
            c_span = soup.find(id="change_value_and_rate")
            if c_span:
                kq_diff, kq_rate, kq_up, kq_down = parse_change_text(c_span.text.strip())
        else:
            # 2차 시도: 일별 시세 테이블 파싱
            d_url = "https://finance.naver.com/sise/sise_index_day.naver?code=KQ150"
            res = requests.get(d_url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            tr = soup.find("table", class_="type_1").find_all("tr")[2]
            tds = tr.find_all("td")
            kq_val = tds[1].text.strip()
            kq_diff, kq_rate, kq_up, kq_down = parse_change_text(tds[2].text + " " + tds[3].text)
    except:
        pass
    results.append({"name": "코스닥 150", "value": kq_val, "change_val": kq_diff, "change_rate": kq_rate, "is_up": kq_up, "is_down": kq_down})

    # 3. VKOSPI (코스피 200 변동성지수)
    vk_val, vk_diff, vk_rate, vk_up, vk_down = "-", "0", 0.0, False, False
    # 1차 시도: 모바일 공식 API
    try:
        vk_url = "https://api.stock.naver.com/index/V-KOSPI200/basic"
        res = requests.get(vk_url, headers=MOBILE_HEADERS, timeout=5)
        if res.status_code == 200:
            data = res.json()
            vk_val = str(data.get("closePrice") or data.get("nowValue", "-"))
            vk_diff = str(data.get("compareToPreviousClosePrice") or data.get("changeValue", "0")).replace("+", "").replace("-", "")
            raw_rate = float(str(data.get("fluctuationsRatio") or data.get("changeRate", "0")).replace("%", "").replace(",", ""))
            vk_rate = abs(raw_rate)
            t_obj = data.get("compareToPreviousPrice", {})
            t_name = t_obj.get("name", "") if isinstance(t_obj, dict) else str(t_obj)
            vk_up = (raw_rate > 0) or ("RISING" in t_name) or ("UP" in t_name)
            vk_down = (raw_rate < 0) or ("FALLING" in t_name) or ("DOWN" in t_name)
    except:
        pass

    # 2차 시도: 네이버 검색 결과 크롤링
    if vk_val == "-":
        try:
            s_url = "https://search.naver.com/search.naver?query=VKOSPI"
            s_res = requests.get(s_url, headers=HEADERS, timeout=5)
            soup = BeautifulSoup(s_res.text, "html.parser")
            price_tag = soup.select_one("strong._price_value, .sise_price strong, .price_info strong")
            if price_tag:
                vk_val = price_tag.text.strip()
                fluct = soup.select_one(".sise_fluctuate, .price_info .change")
                if fluct:
                    vk_diff, vk_rate, vk_up, vk_down = parse_change_text(fluct.text.strip())
        except:
            pass
    results.append({"name": "VKOSPI (변동성)", "value": vk_val, "change_val": vk_diff, "change_rate": vk_rate, "is_up": vk_up, "is_down": vk_down})

    # 4. 원·달러 환율
    fx_val, fx_diff, fx_rate, fx_up, fx_down = "-", "0", 0.0, False, False
    try:
        m_url = "https://finance.naver.com/marketindex/"
        res = requests.get(m_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        box = soup.find("div", class_="head_info")
        if box:
            fx_val = box.find("span", class_="value").text.strip() + "원"
            fx_diff = box.find("span", class_="change").text.strip()
            box_text = box.text
            fx_up = "상승" in box_text
            fx_down = "하락" in box_text
    except:
        pass
    results.append({"name": "원·달러 환율", "value": fx_val, "change_val": fx_diff, "change_rate": fx_rate, "is_up": fx_up, "is_down": fx_down})

    return results

def get_sector_data():
    url = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
    sectors = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        rows = soup.find("table", class_="type_1").find_all("tr")

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
    except:
        pass

    sectors.sort(key=lambda x: x["rate"], reverse=True)
    top_3 = sectors[:3] if len(sectors) >= 3 else sectors
    bot_3 = sectors[-3:] if len(sectors) >= 3 else []
    bot_3.reverse()

    def fetch_stocks(sector_url):
        stocks = []
        try:
            s_res = requests.get(sector_url, headers=HEADERS, timeout=10)
            s_soup = BeautifulSoup(s_res.content.decode('euc-kr', 'replace'), 'html.parser')
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
                        except:
                            pass
                        if len(stocks) == 3:
                            break
        except:
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
        if idx["is_up"]:
            sign = "🔺 +"
            color_class = "text-up"
            badge_bg = "bg-up-light"
        elif idx["is_down"]:
            sign = "🔻 -"
            color_class = "text-down"
            badge_bg = "bg-down-light"
        else:
            sign = "➖ "
            color_class = "text-flat"
            badge_bg = "bg-gray-100"

        if idx["change_rate"] > 0:
            rate_text = f"{sign}{idx['change_rate']:.2f}%"
        elif idx["is_up"]:
            rate_text = "🔺 상승"
        elif idx["is_down"]:
            rate_text = "🔻 하락"
        else:
            rate_text = "➖ 보합"

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
