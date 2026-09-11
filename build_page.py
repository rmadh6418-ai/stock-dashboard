import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import requests
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}

DASHBOARD_URL = "https://rmadh6418-ai.github.io/stock-dashboard/"

# Gemini API 초기화 (환경 변수에 GEMINI_API_KEY 등록 필수)
API_KEY = os.environ.get("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

EXCLUDE_NEWS_KEYWORDS = ["콘서트", "포크", "음악회", "축제", "페스티벌", "공연", "전시회", "문화", "봉사", "기부", "나눔", "장학", "사회공헌", "바자회", "캠페인", "후원", "부고", "부음", "화혼", "결혼", "인사", "동정", "알림", "모집", "채용", "이벤트", "경품", "할인", "프로모션", "쿠폰", "체험단", "선착순", "추첨", "골프대회", "마라톤", "시상식", "장학금", "헌혈", "가을", "여행", "맛집", "포토", "영상", "방송", "예능"]
BUSINESS_NEWS_KEYWORDS = ["실적", "매출", "영업익", "영업이익", "순이익", "수주", "계약", "투자", "공급", "인수", "합병", "M&A", "증설", "공시", "주가", "상승", "하락", "급등", "급락", "수출", "양산", "출시", "기술", "개발", "협력", "제휴", "공장", "가동", "수혜", "흑자", "적자", "전망", "목표가", "배당", "지분", "증자", "특허", "사업", "성장", "솔루션", "생산", "상장", "신제품", "AI", "반도체", "배터리", "로봇", "방산", "원전", "바이오", "임상", "승인", "신약", "수주잔고", "체결", "공급계약"]

KOSPI200_SECTORS = {
    "화학·에너지": ["LG화학", "S-Oil", "SK이노베이션", "롯데케미칼", "SK가스", "GS", "한국가스공사"],
    "이차전지·배터리": ["LG에너지솔루션", "POSCO홀딩스", "포스코퓨처엠", "삼성SDI", "엘앤에프", "에코프로머티", "코스모신소재"],
    "조선·중공업": ["HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양", "한화엔진", "HD현대", "HD현대마린엔진", "HD현대마린솔루션", "대한조선", "한국카본"],
    "전기·전자 (반도체/IT)": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "한미반도체", "LG전자", "이수페타시스", "DB하이텍"],
    "자동차·운송장비": ["현대차", "기아", "현대모비스", "현대오토에버", "현대글로비스", "현대위아", "에스엘"],
    "원전·전력인프라": ["한국전력", "두산에너빌리티", "한전기술", "한전KPS", "효성중공업", "산일전기", "대한전선", "일진전기", "LS ELECTRIC", "HD현대일렉트릭", "LS에코에너지"],
    "방위산업·우주항공": ["한화에어로스페이스", "현대로템", "한국항공우주", "한화시스템", "LIG넥스원"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "유한양행", "한미약품", "SK바이오팜", "삼성에피스홀딩스", "녹십자", "대웅제약"],
    "금융·지주": ["KB금융", "신한지주", "하나금융지주", "메리츠금융지주", "기업은행", "미래에셋증권", "삼성증권", "우리금융지주", "IM금융지주", "삼성생명"],
    "인터넷·플랫폼": ["NAVER", "카카오", "크래프톤"],
    "건설·시공": ["현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "철강·금속": ["고려아연", "현대제철", "동국제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심"],
}

KOSDAQ150_SECTORS = {
    "제약·바이오": ["알테오젠", "HLB", "삼천당제약", "리가켐바이오", "휴젤", "에스티팜", "HK이노엔", "동국제약", "지투지바이오", "디엔디파마텍", "올릭스", "에이비엘바이오", "파마리서치", "펩트론", "오스코텍", "엘앤씨바이오", "실리콘투", "클래시스"],
    "이차전지·소재": ["에코프로비엠", "에코프로", "엔켐", "대주전자재료", "서진시스템", "나노신소재", "피엔티", "동화기업", "한중엔시에스"],
    "반도체 소부장": ["HPSP", "리노공업", "주성엔지니어링", "이오테크닉스", "솔브레인", "동진쎄미켐", "티씨케이", "ISC", "하나머티리얼즈", "대덕전자", "유진테크", "심텍", "원익IPS", "테크윙", "파크시스템스", "두산테스나", "필옵틱스", "씨엠티엑스", "원익QnC"],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드"],
    "로봇·자동화": ["레인보우로보틱스", "로보티즈", "에스에프에이", "휴림로봇", "로보스타", "에스피지", "하이젠알앤엠", "삼현", "유일로보틱스"],
    "피팅·배관기자재": ["성광벤드", "태광", "하이록코리아"],
}

def generate_ai_sector_summary(sec_name, rate, matched_stocks, news_items):
    """Gemini 1.5 Flash 모델을 활용한 실제 섹터 심층 분석"""
    if not API_KEY:
        stock_str = ", ".join([f"{s['name']}({s['rate']:+.2f}%)" for s in matched_stocks[:2]])
        return f"{stock_str} 등 주요 종목을 중심으로 섹터 전반이 {rate:+.2f}% 변동했습니다. (AI 분석기 비활성화 상태)"
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        stock_info = ", ".join([f"{s['name']}({s['rate']:+.2f}%)" for s in matched_stocks[:3]])
        news_info = ", ".join([n['title'] for n in news_items]) if news_items else "특이 뉴스 없음"
        
        prompt = f"""
        한국 증시 '{sec_name}' 섹터 마감/실시간 데이터를 분석하라.
        - 전체 섹터 평균 등락률: {rate:+.2f}%
        - 섹터 내 주요 변동 종목: {stock_info}
        - 관련 주요 언론 보도: {news_info}
        
        위 데이터를 바탕으로 해당 섹터의 당일 주가 움직임 원인과 핵심 모멘텀을 전문 펀드매니저 시각에서 2~3문장으로 분석하라.
        마크다운이나 특수문자를 제외하고 단답형 평문으로만 작성하라.
        """
        response = model.generate_content(prompt)
        return response.text.strip().replace('\n', ' ')
    except Exception as e:
        # API 할당량 초과 등 오류 발생 시 백업 텍스트 제공
        stock_str = ", ".join([f"{s['name']}({s['rate']:+.2f}%)" for s in matched_stocks[:2]])
        return f"{stock_str} 등 핵심 종목이 변동을 주도했습니다. (현재 AI 서버 지연으로 요약을 생략합니다.)"

def get_news_score(title, stock_name):
    for bad in EXCLUDE_NEWS_KEYWORDS:
        if bad in title: return -1
    score = 0
    aliases = [stock_name]
    if stock_name == "S-Oil": aliases.extend(["에쓰오일", "SOil", "S-OIL"])
    elif "홀딩스" in stock_name: aliases.append(stock_name.replace("홀딩스", ""))
    
    has_stock = any(alias in title for alias in aliases if len(alias) >= 2)
    has_biz = any(biz in title for biz in BUSINESS_NEWS_KEYWORDS)
    
    if has_stock: score += 5
    if has_biz: score += 4
    if not has_stock and not has_biz: return -1
    return score

def fetch_real_news(keyword, stock_code=""):
    candidates = []
    if stock_code:
        try:
            url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page=1"
            res = requests.get(url, headers=HEADERS, timeout=4)
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
        except: pass
    
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:2]

def get_exchange_rate():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta = res.json()['chart']['result'][0]['meta']
        price = meta['regularMarketPrice']
        prev = meta['previousClose']
        diff = price - prev
        rate = (diff / prev) * 100
        return {
            "name": "원·달러 환율", "code_key": "FX_USDKRW",
            "value": f"{price:,.2f}원", "change_val": f"{diff:+.2f}원",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except Exception:
        return {"name": "원·달러 환율", "code_key": "FX_USDKRW", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_us_10y_yield():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/^TNX"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta = res.json()['chart']['result'][0]['meta']
        price = meta['regularMarketPrice']
        prev = meta['previousClose']
        diff = price - prev
        rate = (diff / prev) * 100
        return {
            "name": "미국채 10년물", "code_key": "US10Y",
            "value": f"{price:.3f}%", "change_val": f"{abs(diff):.3f}bp",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except:
        return {"name": "미국채 10년물", "code_key": "US10Y", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_investor_trend():
    """네이버 금융 메인 구조에 맞춘 수급(외국인/기관/개인) 파싱 (버그 완벽 수정)"""
    trends = {"KOSPI": "데이터 수집 중", "KOSDAQ": "데이터 수집 중"}
    try:
        res = requests.get("https://finance.naver.com/", headers=HEADERS, timeout=6)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        
        for market, cls in [("KOSPI", "kospi_area"), ("KOSDAQ", "kosdaq_area")]:
            area = soup.find("div", class_=cls)
            if area:
                dl = area.find("dl", class_="dl_invest")
                if dl:
                    dds = dl.find_all("dd")
                    parsed = []
                    for dd in dds:
                        text = dd.text.strip().replace('\n', '').replace('\t', '')
                        if text:
                            parsed.append(text)
                    if parsed:
                        trends[market] = " | ".join(parsed)
    except Exception as e:
        print(f"Investor Trend Error: {e}")
    return trends

def get_market_indices():
    targets = [
        ("코스피 (KOSPI)", "KOSPI", "https://m.stock.naver.com/api/index/KOSPI/basic"),
        ("코스닥 (KOSDAQ)", "KOSDAQ", "https://m.stock.naver.com/api/index/KOSDAQ/basic"),
        ("코스피 200", "KPI200", "https://m.stock.naver.com/api/index/KPI200/basic"),
    ]
    results = []
    
    def fetch_index(target):
        name, key, url = target
        try:
            res = requests.get(url, headers=HEADERS, timeout=4).json()
            cd = str(res.get("compareToPreviousPrice", {}).get("code", "3"))
            return {
                "name": name, "code_key": key, "value": res.get("closePrice", "-"),
                "change_val": res.get("compareToPreviousClosePrice", "0"),
                "change_rate": abs(float(res.get("fluctuationsRatio", 0))),
                "is_up": cd in ["1", "2"], "is_down": cd in ["4", "5"]
            }
        except: return {"name": name, "code_key": key, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_index, targets))
    
    results.append(get_exchange_rate())
    results.append(get_us_10y_yield())
    return results

def get_market_stocks():
    """네이버 봇 감지(IP Block) 방지를 위해 시총 데이터는 '순차적으로' 안전하게 가져옵니다."""
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
                            href = a_tag.get("href", "")
                            code_match = re.search(r"code=(\d+)", href)
                            code = code_match.group(1) if code_match else ""
                            price = tds[2].text.strip()
                            rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
                            try:
                                stocks[name] = {"price": price, "rate": float(rate_text), "code": code, "market": market}
                            except Exception:
                                pass
        except Exception as e:
            print(f"Stock fetch error on {u}: {e}")
    return stocks

def calculate_sectors(sector_dict, stock_data):
    def process_sector(sec_name, stock_names):
        try:
            matched = []
            for sname in stock_names:
                if sname in stock_data:
                    matched.append({"name": sname, **stock_data[sname]})
            
            if not matched: 
                return None
            
            matched.sort(key=lambda x: abs(x["rate"]), reverse=True)
            top_stock = matched[0]
            avg_r = sum(s["rate"] for s in matched) / len(matched)
            news_items = fetch_real_news(top_stock["name"], top_stock.get("code", ""))
            
            # AI 분석 함수 호출
            summary_text = generate_ai_sector_summary(sec_name, avg_r, matched, news_items)
            
            return {
                "name": sec_name, "rate": round(avg_r, 2), "stocks": matched[:3],
                "lead_stock": top_stock["name"], "summary": summary_text, "news": news_items,
            }
        except Exception as e:
            return None

    results = []
    # 제미나이 API 한도 초과(Rate Limit) 방지를 위해 worker를 3개로 낮춤
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(process_sector, k, v) for k, v in sector_dict.items()]
        for future in as_completed(futures):
            res = future.result()
            if res: results.append(res)
            
    results.sort(key=lambda x: x["rate"], reverse=True)
    return results[:3], results[-3:][::-1]

def render_html(indices, k200_top, k200_bot, k150_top, k150_bot, investor_trends):
    index_cards = ""
    for idx in indices:
        sign = "▲ +" if idx["is_up"] else ("▼ -" if idx["is_down"] else "― ")
        color_class = "text-up" if idx["is_up"] else ("text-down" if idx["is_down"] else "text-flat")
        badge_bg = "bg-up-light" if idx["is_up"] else ("bg-down-light" if idx["is_down"] else "bg-gray-100")
        diff_text = f" ({idx['change_val']})" if idx["change_val"] != "0" else ""
        
        index_cards += f"""
        <div class="card" data-index-target="{idx['code_key']}">
            <div class="card-title">{idx['name']}</div>
            <div class="card-value" id="val-{idx['code_key']}">{idx['value']}</div>
            <div class="badge {badge_bg} {color_class}" id="badge-{idx['code_key']}">{sign}{abs(idx['change_rate']):.2f}%{diff_text}</div>
        </div>
        """

    trend_html = f"""
    <div class="investor-trend-box">
        <div class="trend-row"><span class="trend-label">KOSPI 수급</span> <span class="trend-data">{investor_trends.get('KOSPI', '집계중')}</span></div>
        <div class="trend-row"><span class="trend-label">KOSDAQ 수급</span> <span class="trend-data">{investor_trends.get('KOSDAQ', '집계중')}</span></div>
    </div>
    """

    def build_sector_list(sectors):
        if not sectors: 
            return '<div class="sector-item" style="color:#ef4444; font-weight:700;">섹터 로딩 오류가 발생했습니다. (데이터를 가져오는 중 일시적인 서버 차단이 발생했습니다.)</div>'
        html = ""
        for s in sectors:
            r = s["rate"]
            color_class = "text-up" if r > 0 else ("text-down" if r < 0 else "text-flat")
            stock_tags = "".join([f'<span class="stock-pill"><span class="stock-name">{st["name"]}</span> <b class="stock-rate {"text-up" if st["rate"]>0 else "text-down"}">{st["rate"]:+.2f}%</b> <span class="stock-price">({st["price"]}원)</span></span>' for st in s.get("stocks", [])])
            news_tags = "".join([f'<div class="sector-news">📰 <a href="{n["link"]}" target="_blank" class="news-link">{n["title"]}</a></div>' for n in s.get("news", [])[:1]])
            
            html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{r:+.2f}%</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
                <div class="sector-summary"><span class="summary-badge">🤖 AI 분석</span> {s.get("summary", "")}</div>
                {news_tags}
            </div>
            """
        return html

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
        h1 {{ font-size: 1.45rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 12px; }}
        .card {{ background: #fff; padding: 16px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.82rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.30rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .badge {{ display: inline-block; font-size: 0.78rem; font-weight: 700; padding: 3px 10px; border-radius: 6px; }}
        
        .investor-trend-box {{ background: #fff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px 16px; margin-bottom: 24px; font-size: 0.85rem; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
        .trend-row {{ margin-bottom: 6px; }}
        .trend-row:last-child {{ margin-bottom: 0; }}
        .trend-label {{ font-weight: 800; color: #334155; display: inline-block; width: 90px; }}
        .trend-data {{ color: #0f172a; font-weight: 600; }}

        .group-title {{ font-size: 1.15rem; font-weight: 800; margin: 26px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #cbd5e1; }}
        .section-title {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 16px; margin-bottom: 18px; }}
        .sector-item {{ padding: 14px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .sector-name {{ font-weight: 800; font-size: 1.02rem; }}
        
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 9px; font-size: 0.82rem; }}
        
        .sector-summary {{ font-size: 0.86rem; line-height: 1.55; color: #1e293b; background: #eff6ff; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; border-left: 3px solid #3b82f6; font-weight: 500; }}
        .summary-badge {{ font-weight: 800; color: #1d4ed8; display: inline-block; margin-right: 4px; }}
        
        .text-up {{ color: #e11d48 !important; font-weight: 700; }}
        .text-down {{ color: #2563eb !important; font-weight: 700; }}
        .text-flat {{ color: #64748b !important; font-weight: 700; }}
        .bg-up-light {{ background-color: #ffe4e6 !important; }}
        .bg-down-light {{ background-color: #dbeafe !important; }}
        .bg-gray-100 {{ background-color: #f1f5f9 !important; }}
    </style>
</head>
<body>
    <header><h1>📊 실시간 국내 증시 대시보드</h1></header>
    <div class="grid-indices">{index_cards}</div>
    {trend_html}
    
    <div class="group-title">🏢 코스피 200 업종 동향</div>
    <div class="section-title">🔴 코스피 200 강세 업종</div><div class="sector-box">{build_sector_list(k200_top)}</div>
    <div class="section-title">🔵 코스피 200 약세 업종</div><div class="sector-box">{build_sector_list(k200_bot)}</div>

    <div class="group-title">🚀 코스닥 150 업종 동향</div>
    <div class="section-title">🔴 코스닥 150 강세 업종</div><div class="sector-box">{build_sector_list(k150_top)}</div>
    <div class="section-title">🔵 코스닥 150 약세 업종</div><div class="sector-box">{build_sector_list(k150_bot)}</div>
</body>
</html>
"""
    os.makedirs("public", exist_ok=True)
    with open("public/index.html", "w", encoding="utf-8") as f:
        f.write(template)

if __name__ == "__main__":
    # 데이터별 충돌 방지를 위해 멀티스레드로 각 기능을 분산 호출합니다.
    with ThreadPoolExecutor(max_workers=3) as executor:
        f_indices = executor.submit(get_market_indices)
        f_stocks = executor.submit(get_market_stocks)
        f_investor = executor.submit(get_investor_trend)
        
        indices = f_indices.result()
        stock_data = f_stocks.result()
        investor_trends = f_investor.result()

    k200_top, k200_bot = calculate_sectors(KOSPI200_SECTORS, stock_data)
    k150_top, k150_bot = calculate_sectors(KOSDAQ150_SECTORS, stock_data)

    render_html(indices, k200_top, k200_bot, k150_top, k150_bot, investor_trends)
