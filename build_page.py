import os
import re
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://finance.naver.com/"
}

def parse_change_text(text):
    """문자열에서 등락폭, 등락률, 부호 추출"""
    is_up = ("상승" in text) or ("+" in text) or ("▲" in text)
    is_down = ("하락" in text) or ("-" in text) or ("▼" in text)
    nums = re.findall(r'[\d\.,]+', text)
    diff = nums[0] if len(nums) >= 1 else "0"
    rate = 0.0
    if len(nums) >= 2:
        try:
            rate = abs(float(nums[1].replace(',', '')))
        except Exception:
            rate = 0.0
    return diff, rate, is_up, is_down

def fetch_vkospi(kospi_val):
    """VKOSPI 전용 5중 교차 수집 엔진 (트레이딩뷰 -> 구글파이낸스 -> 인베스팅 프록시 -> KRX -> 다음)"""
    
    # 1. 트레이딩뷰 코리아 스캐너 API (클라우드 IP 차단 없음, 실시간 공식 데이터)
    try:
        tv_url = "https://scanner.tradingview.com/korea/scan"
        payload = {
            "symbols": {"tickers": ["KRX:VKOSPI", "INDEX:VKOSPI"]},
            "columns": ["close", "change", "change_abs"]
        }
        res = requests.post(tv_url, json=payload, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code == 200:
            data = res.json().get("data", [])
            for item in data:
                d = item.get("d", [])
                if d and len(d) >= 3 and d[0] is not None:
                    val = float(d[0])
                    if 5.0 <= val <= 100.0:
                        pct = abs(float(d[1])) if d[1] is not None else 0.0
                        diff = abs(float(d[2])) if d[2] is not None else 0.0
                        return f"{val:.2f}", f"{diff:.2f}", round(pct, 2), d[1] > 0, d[1] < 0
    except Exception:
        pass

    # 2. 구글 파이낸스 인덱스 수집
    for g_code in ["VKOSPI:INDEXKRX", "VKOSPI:KRX"]:
        try:
            g_url = f"https://www.google.com/finance/quote/{g_code}"
            g_res = requests.get(g_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            if g_res.status_code == 200:
                soup = BeautifulSoup(g_res.text, "html.parser")
                p_el = soup.select_one(".YMlKec.fxKbKc")
                if p_el:
                    clean_p = p_el.text.strip().replace(",", "")
                    val = float(clean_p)
                    if 5.0 <= val <= 100.0:
                        chg_el = soup.select_one(".JwB6be, .P2Luy")
                        diff, rate, is_up, is_down = parse_change_text(chg_el.text if chg_el else "")
                        return f"{val:.2f}", diff, rate, is_up, is_down
        except Exception:
            pass

    # 3. 인베스팅닷컴 전용 API 프록시 우회
    try:
        target = urllib.parse.quote("https://kr.investing.com/indices/kospi-200-volatility")
        proxy_url = f"https://api.allorigins.win/get?url={target}"
        p_res = requests.get(proxy_url, timeout=8)
        if p_res.status_code == 200:
            html = p_res.json().get("contents", "")
            soup = BeautifulSoup(html, "html.parser")
            price_el = soup.select_one('[data-test="instrument-price-last"]')
            if price_el:
                val = float(price_el.text.strip().replace(",", ""))
                if 5.0 <= val <= 100.0:
                    diff_el = soup.select_one('[data-test="instrument-price-change"]')
                    rate_el = soup.select_one('[data-test="instrument-price-change-percent"]')
                    diff = diff_el.text.strip().replace("+", "").replace("-", "") if diff_el else "0"
                    rate_raw = rate_el.text.strip() if rate_el else "0"
                    rate_val = abs(float(re.sub(r'[^\d\.]', '', rate_raw))) if re.search(r'\d', rate_raw) else 0.0
                    return f"{val:.2f}", diff, rate_val, "+" in (diff_el.text if diff_el else ""), "-" in (diff_el.text if diff_el else "")
    except Exception:
        pass

    # 4. 한국거래소(KRX) 전략/변동성 지수 테이블(04) 수집
    try:
        krx_url = "http://data.krx.co.kr/comm/bldAttPage/getJsonData.cmd"
        krx_headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://data.krx.co.kr/"}
        krx_data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT00101",
            "idxIndMidClssCd": "04",
            "money": "1",
            "csvxls_isNo": "false"
        }
        res = requests.post(krx_url, headers=krx_headers, data=krx_data, timeout=5)
        if res.status_code == 200:
            for item in res.json().get("output", []):
                nm = item.get("IDX_NM", "")
                if "변동성" in nm or "VKOSPI" in nm:
                    val_str = item.get("CLSPRC_IDX", "").replace(",", "")
                    val = float(val_str)
                    if 5.0 <= val <= 100.0:
                        diff = item.get("PRV_DD_CMPR", "0").replace(",", "")
                        rate = abs(float(str(item.get("UPDN_RATE", "0")).replace(",", "")))
                        fluc = item.get("FLUC_TP_CD", "3")
                        return f"{val:.2f}", diff, rate, fluc == "1", fluc == "2"
    except Exception:
        pass

    # 5. 다음 금융 전용 지수 API (U028)
    try:
        d_url = "https://finance.daum.net/api/quotes/U028"
        d_headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.daum.net/quotes/U028"}
        d_res = requests.get(d_url, headers=d_headers, timeout=5)
        if d_res.status_code == 200:
            d_json = d_res.json()
            val = float(d_json.get("tradePrice", 0))
            if 5.0 <= val <= 100.0:
                diff = str(d_json.get("changePrice", "0"))
                rate = abs(float(d_json.get("changeRate", 0)) * 100)
                chg = d_json.get("change", "")
                return f"{val:.2f}", diff, round(rate, 2), "RISE" in chg or "UP" in chg, "FALL" in chg or "DOWN" in chg
    except Exception:
        pass

    return "-", "0", 0.0, False, False

def get_market_indices():
    results = []
    main_url = "https://finance.naver.com/sise/"
    kospi_val = "-"
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
                if name == "코스피 (KOSPI)":
                    kospi_val = price
                c_text = change_elem.text.strip() if change_elem else ""
                diff, rate, is_up, is_down = parse_change_text(c_text)
                results.append({
                    "name": name, "value": price, "change_val": diff,
                    "change_rate": rate, "is_up": is_up, "is_down": is_down
                })
            else:
                results.append({"name": name, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})
    except Exception:
        for name in ["코스피 (KOSPI)", "코스닥 (KOSDAQ)", "코스피 200"]:
            results.append({"name": name, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})

    # VKOSPI 수집 (코스피 값 오염 방지 검증 탑재)
    vk_val, vk_diff, vk_rate, vk_up, vk_down = fetch_vkospi(kospi_val)
    results.append({
        "name": "VKOSPI (변동성)", "value": vk_val, "change_val": vk_diff,
        "change_rate": vk_rate, "is_up": vk_up, "is_down": vk_down
    })

    # 원·달러 환율
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
            fx_up = ("상승" in box_text) or ("+" in box_text)
            fx_down = ("하락" in box_text) or ("-" in box_text)
    except Exception:
        pass
    results.append({
        "name": "원·달러 환율", "value": fx_val, "change_val": fx_diff,
        "change_rate": fx_rate, "is_up": fx_up, "is_down": fx_down
    })
    return results

def get_market_stocks():
    stocks = {}
    urls = [
        ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1", "KOSPI"),
        ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=2", "KOSPI"),
        ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=1", "KOSDAQ"),
        ("https://finance.naver.com/sise/sise_market_sum.naver?sosok=1&page=2", "KOSDAQ")
    ]
    for u, market in urls:
        try:
            res = requests.get(u, headers=HEADERS, timeout=8)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            table = soup.find("table", class_="type_2")
            if table:
                for tr in table.find_all("tr"):
                    tds = tr.find_all("td")
                    if len(tds) >= 5:
                        a_tag = tds[1].find("a")
                        if a_tag:
                            name = a_tag.text.strip()
                            price = tds[2].text.strip()
                            rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
                            try:
                                rate_val = float(rate_text)
                                stocks[name] = {"price": price, "rate": rate_val, "market": market}
                            except Exception:
                                pass
        except Exception:
            pass
    return stocks

KOSPI200_SECTORS = {
    "화학·에너지": ["LG화학", "S-Oil", "SK이노베이션", "롯데케미칼"],
    "이차전지·배터리": ["LG에너지솔루션", "POSCO홀딩스", "포스코퓨처엠", "삼성SDI"],
    "조선·중공업": ["HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양"],
    "전기·전자 (반도체/IT)": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍"],
    "자동차·운송장비": ["현대차", "기아", "현대모비스"],
    "원전·전력인프라": ["한국전력", "두산에너빌리티", "한전기술", "한전KPS"],
    "방위산업·우주항공": ["한화에어로스페이스", "현대로템", "한국항공우주"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "유한양행", "한미약품"],
    "금융·지주": ["KB금융", "신한지주", "하나금융지주", "메리츠금융지주"],
    "인터넷·플랫폼": ["NAVER", "카카오", "크래프톤"],
    "건설·시공": ["현대건설", "대우건설", "GS건설"],
    "철강·금속": ["고려아연", "현대제철", "동국제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심"]
}

KOSDAQ150_SECTORS = {
    "제약·바이오": ["알테오젠", "HLB", "삼천당제약", "리가켐바이오", "휴젤", "에스티팜"],
    "이차전지·소재": ["에코프로비엠", "에코프로", "엔켐", "대주전자재료"],
    "반도체 소부장": ["HPSP", "리노공업", "주성엔지니어링", "이오테크닉스", "솔브레인", "동진쎄미켐"],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드"],
    "로봇·자동화": ["레인보우로보틱스", "로보티즈", "에스에프에이"],
    "피팅·배관기자재": ["성광벤드", "태광", "하이록코리아"]
}

def calculate_sectors(sector_dict, stock_data):
    results = []
    for sec_name, stock_names in sector_dict.items():
        matched = []
        rates = []
        for sname in stock_names:
            if sname in stock_data:
                item = stock_data[sname]
                matched.append({"name": sname, "rate": item["rate"], "price": item["price"]})
                rates.append(item["rate"])
        if matched:
            avg_r = sum(rates) / len(rates)
            results.append({"name": sec_name, "rate": round(avg_r, 2), "stocks": matched[:3]})
    results.sort(key=lambda x: x["rate"], reverse=True)
    top = results[:3]
    bot = results[-3:]
    bot.reverse()
    return top, bot

def generate_market_review(indices, k200_top, k200_bot, k150_top, k150_bot):
    """당일 수집 데이터를 심층 분석하여 전문가 수준의 마감 시황 리뷰를 자동 생성"""
    kospi = next((x for x in indices if "코스피 (KOSPI)" in x["name"]), {})
    kosdaq = next((x for x in indices if "코스닥 (KOSDAQ)" in x["name"]), {})
    vkospi = next((x for x in indices if "VKOSPI" in x["name"]), {})
    fx = next((x for x in indices if "환율" in x["name"]), {})

    # 지수 흐름 분석
    k_dir = "상승" if kospi.get("is_up") else ("하락" if kospi.get("is_down") else "보합")
    kq_dir = "상승" if kosdaq.get("is_up") else ("하락" if kosdaq.get("is_down") else "보합")

    # 코스피 200 주도/부진 섹터 분석
    k200_top_names = [f"<b>{s['name']}</b>(+{s['rate']}%)" for s in k200_top[:2]]
    k200_bot_names = [f"<b>{s['name']}</b>({s['rate']}%)" for s in k200_bot[:2]]
    
    # 코스닥 150 주도/부진 섹터 분석
    k150_top_names = [f"<b>{s['name']}</b>(+{s['rate']}%)" for s in k150_top[:2]]
    k150_bot_names = [f"<b>{s['name']}</b>({s['rate']}%)" for s in k150_bot[:2]]

    # 변동성 및 환율 코멘트
    fx_text = ""
    if fx.get("is_down"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 하향 안정화(원화 강세)를 보이며 외국인 수급에 긍정적인 여건을 형성했습니다."
    elif fx.get("is_up"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 상승하며 환율 변동성에 대한 주의가 지속되고 있습니다."
    else:
        fx_text = f"원·달러 환율은 <b>{fx.get('value')}</b> 선에서 보합권 흐름을 나타냈습니다."

    vk_text = ""
    if vkospi.get("value") != "-":
        if vkospi.get("is_down"):
            vk_text = f"변동성지수(VKOSPI)는 <b>{vkospi.get('value')}</b>로 안정세를 유지하며 시장 내 과도한 불안 심리는 완화된 양상입니다."
        else:
            vk_text = f"변동성지수(VKOSPI)는 <b>{vkospi.get('value')}</b>로 소폭 고개를 들며 상방 탄력성 대비 파생 시장의 경계 심리가 상존하고 있습니다."

    review_html = f"""
    <div class="review-card">
        <div class="review-header">
            <span class="review-title">📝 정규장 마감 핵심 요약 & 섹터 리뷰</span>
            <span class="review-tag">AI 데일리 마켓 브리핑</span>
        </div>
        <div class="review-body">
            <div class="review-item">
                <span class="bullet">🔹</span>
                <div><b>[시장 총평]</b> 코스피는 <b>{kospi.get('value')}</b>({k_dir}), 코스닥은 <b>{kosdaq.get('value')}</b>({kq_dir})으로 정규장을 마감했습니다. 양대 지수는 주도 섹터 중심의 차별화 장세를 이어갔습니다.</div>
            </div>
            <div class="review-item">
                <span class="bullet">🔹</span>
                <div><b>[코스피 200 동향]</b> 대형주 시장에서는 {', '.join(k200_top_names)} 등이 매수세를 이끌며 지수를 주도했습니다. 반면 차익 실현 매물이 출회된 {', '.join(k200_bot_names)} 등은 상대적으로 약세를 기록했습니다.</div>
            </div>
            <div class="review-item">
                <span class="bullet">🔹</span>
                <div><b>[코스닥 150 동향]</b> 코스닥 핵심 종목군에서는 {', '.join(k150_top_names)} 업종이 강한 탄력성을 시현했으며, {', '.join(k150_bot_names)} 업종은 조정세를 보이며 업종별 순환매가 뚜렷했습니다.</div>
            </div>
            <div class="review-item">
                <span class="bullet">🔹</span>
                <div><b>[리스크 지표]</b> {fx_text} {vk_text}</div>
            </div>
        </div>
    </div>
    """
    return review_html

def render_html(indices, k200_top, k200_bot, k150_top, k150_bot):
    now_str = datetime.now().strftime("%Y년 %m월 %d일 %H:%M 마감 기준")
    
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

        if idx["change_rate"] > 0:
            rate_text = f"{sign}{idx['change_rate']:.2f}%"
        elif idx["is_up"]:
            rate_text = "▲ 상승"
        elif idx["is_down"]:
            rate_text = "▼ 하락"
        else:
            rate_text = "― 보합"

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
        sign = "▲ +" if is_up else "▼ "
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

    review_section = generate_market_review(indices, k200_top, k200_bot, k150_top, k150_bot)

    template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>국내 정규장 마감 대시보드</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: #f4f6f9; color: #1e293b; padding: 16px; max-width: 960px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 20px; }}
        h1 {{ font-size: 1.45rem; font-weight: 800; color: #0f172a; margin-bottom: 4px; }}
        .timestamp {{ font-size: 0.85rem; color: #64748b; }}
        
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 20px; }}
        .card {{ background: #fff; padding: 14px 10px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.8rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.2rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .badge {{ display: inline-block; font-size: 0.75rem; font-weight: 700; padding: 2px 8px; border-radius: 6px; }}
        
        /* 마감 리뷰 브리핑 박스 스타일 */
        .review-card {{ background: #ffffff; border-radius: 12px; border-left: 4px solid #3b82f6; border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; padding: 16px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }}
        .review-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px; }}
        .review-title {{ font-size: 1.05rem; font-weight: 800; color: #1e293b; }}
        .review-tag {{ font-size: 0.75rem; font-weight: 700; color: #2563eb; background: #eff6ff; padding: 3px 8px; border-radius: 6px; }}
        .review-body {{ display: flex; flex-direction: column; gap: 8px; font-size: 0.9rem; line-height: 1.55; color: #334155; }}
        .review-item {{ display: flex; align-items: flex-start; gap: 6px; }}
        .bullet {{ color: #3b82f6; font-size: 0.8rem; margin-top: 2px; }}

        .group-title {{ font-size: 1.15rem; font-weight: 800; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #cbd5e1; color: #0f172a; }}
        .section-title {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 14px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
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

    {review_section}

    <div class="group-title">🏢 코스피 200 업종 동향</div>
    <div class="section-title">🔴 코스피 200 등락률 상위 업종</div>
    <div class="sector-box">
        {build_sector_list(k200_top, is_up=True)}
    </div>
    <div class="section-title">🔵 코스피 200 등락률 하위 업종</div>
    <div class="sector-box">
        {build_sector_list(k200_bot, is_up=False)}
    </div>

    <div class="group-title">🚀 코스닥 150 업종 동향</div>
    <div class="section-title">🔴 코스닥 150 등락률 상위 업종</div>
    <div class="sector-box">
        {build_sector_list(k150_top, is_up=True)}
    </div>
    <div class="section-title">🔵 코스닥 150 등락률 하위 업종</div>
    <div class="sector-box">
        {build_sector_list(k150_bot, is_up=False)}
    </div>
</body>
</html>
"""
    os.makedirs("public", exist_ok=True)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(template)

if __name__ == "__main__":
    indices = get_market_indices()
    stock_data = get_market_stocks()
    k200_top, k200_bot = calculate_sectors(KOSPI200_SECTORS, stock_data)
    k150_top, k150_bot = calculate_sectors(KOSDAQ150_SECTORS, stock_data)
    render_html(indices, k200_top, k200_bot, k150_top, k150_bot)
