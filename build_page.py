import os
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

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

def get_market_indices():
    """상단 4대 주요 지수 (코스피, 코스닥, 코스피 200, 환율)"""
    results = []
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
                    "name": name, "value": price, "change_val": diff,
                    "change_rate": rate, "is_up": is_up, "is_down": is_down
                })
            else:
                results.append({"name": name, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})
    except Exception:
        for name in ["코스피 (KOSPI)", "코스닥 (KOSDAQ)", "코스피 200"]:
            results.append({"name": name, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False})

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
    """시가총액 상위 종목 체결가, 등락률 및 종목코드 수집"""
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
                            href = a_tag.get("href", "")
                            code_match = re.search(r'code=(\d+)', href)
                            code = code_match.group(1) if code_match else ""
                            price = tds[2].text.strip()
                            rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
                            try:
                                rate_val = float(rate_text)
                                stocks[name] = {"price": price, "rate": rate_val, "code": code, "market": market}
                            except Exception:
                                pass
        except Exception:
            pass
    return stocks

def fetch_real_news(keyword, stock_code=""):
    """네이버 금융 실시간 언론사 뉴스 헤드라인 크롤링"""
    news_list = []
    
    # 1. 종목 코드가 있을 경우: 해당 종목의 네이버 금융 공식 뉴스 크롤링
    if stock_code:
        try:
            url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page=1"
            res = requests.get(url, headers=HEADERS, timeout=5)
            soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
            table = soup.find("table", class_="type5")
            if table:
                for tr in table.find_all("tr"):
                    td_title = tr.find("td", class_="title")
                    td_info = tr.find("td", class_="info")
                    if td_title and td_title.find("a"):
                        a_tag = td_title.find("a")
                        title = a_tag.text.strip()
                        link = "https://finance.naver.com" + a_tag["href"]
                        press = td_info.text.strip() if td_info else "증권뉴스"
                        news_list.append({"title": title, "press": press, "link": link})
                        if len(news_list) >= 2:
                            return news_list
        except Exception:
            pass

    # 2. 키워드 기반 네이버 금융 통합 뉴스 크롤링
    try:
        enc_query = urllib.parse.quote(keyword, encoding='euc-kr')
        url = f"https://finance.naver.com/news/news_search.naver?q={enc_query}"
        res = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        dl_list = soup.find_all("dl", class_="articleList") or soup.find_all("dl")
        for dl in dl_list:
            dt = dl.find("dd", class_="articleSubject") or dl.find("dt")
            if dt and dt.find("a"):
                a_tag = dt.find("a")
                title = a_tag.text.strip()
                link = "https://finance.naver.com" + a_tag["href"]
                summary = dl.find("dd", class_="articleSummary")
                press = summary.find("span", class_="press").text.strip() if summary and summary.find("span", class_="press") else "네이버뉴스"
                news_list.append({"title": title, "press": press, "link": link})
                if len(news_list) >= 2:
                    return news_list
    except Exception:
        pass

    return news_list

KOSPI200_SECTORS = {
    "화학·에너지": ["LG화학", "S-Oil", "SK이노베이션", "롯데케미칼", "SK가스", "GS", "한국가스공사"],
    "이차전지·배터리": ["LG에너지솔루션", "POSCO홀딩스", "포스코퓨처엠", "삼성SDI", "엘앤에프", "에코프로머티],
    "조선·중공업": ["HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양", "한화엔진", "HD현대", "HD현대마린엔진", "HD현대마린솔루션"],
    "전기·전자 (반도체/IT)": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "한미반도체", ],
    "자동차·운송장비": ["현대차", "기아", "현대모비스"],
    "원전·전력인프라": ["한국전력", "두산에너빌리티", "한전기술", "한전KPS", "효성중공업", "산일전기", "대한전선", "일진전기", "LS ELECTRIC", "HD현대일텍트릭"],
    "방위산업·우주항공": ["한화에어로스페이스", "현대로템", "한국항공우주", "한화시스템", "LIG디펜스앤에어로스페이스"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "유한양행", "한미약품", "SK바이오팜"],
    "금융·지주": ["KB금융", "신한지주", "하나금융지주", "메리츠금융지주", "기업은행", "미래에셋증권", "삼성증권", "우리금융지주"],
    "인터넷·플랫폼": ["NAVER", "카카오", "크래프톤"],
    "건설·시공": ["현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "철강·금속": ["고려아연", "현대제철", "동국제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심"]
}

KOSDAQ150_SECTORS = {
    "제약·바이오": ["알테오젠", "HLB", "삼천당제약", "리가켐바이오", "휴젤", "에스티팜", "HK이노엔", "동국제약", "삼천당제약", "지투지바이오", "디엔디파마텍", "올릭스"],
    "이차전지·소재": ["에코프로비엠", "에코프로", "엔켐", "대주전자재료", "서진시스템", "나노신소재", "피엔티", "],
    "반도체 소부장": ["HPSP", "리노공업", "주성엔지니어링", "이오테크닉스", "솔브레인", "동진쎄미켐", "티씨케이", "ISC", "하나머티리얼즈", "대덕전자", "유진테크", "심텍", "원익IPS", "DB하이텍", "테크윙", "파크시스템스"],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드"],
    "로봇·자동화": ["레인보우로보틱스", "로보티즈", "에스에프에이", "휴림로봇", "로보스타", "에스피지", "하이젠알앤엠", "삼현"],
    "피팅·배관기자재": ["성광벤드", "태광", "하이록코리아"]
}

def calculate_sectors(sector_dict, stock_data):
    results = []
    for sec_name, stock_names in sector_dict.items():
        matched = []
        rates = []
        top_stock_code = ""
        for sname in stock_names:
            if sname in stock_data:
                item = stock_data[sname]
                matched.append({"name": sname, "rate": item["rate"], "price": item["price"], "code": item.get("code", "")})
                rates.append(item["rate"])
        if matched:
            matched.sort(key=lambda x: abs(x["rate"]), reverse=True)
            top_stock_name = matched[0]["name"]
            top_stock_code = matched[0].get("code", "")
            
            # 실시간 실제 언론사 뉴스 수집
            news_items = fetch_real_news(top_stock_name, top_stock_code)
            avg_r = sum(rates) / len(rates)
            results.append({
                "name": sec_name,
                "rate": round(avg_r, 2),
                "stocks": matched[:3],
                "lead_stock": top_stock_name,
                "news": news_items
            })
    results.sort(key=lambda x: x["rate"], reverse=True)
    top = results[:3]
    bot = results[-3:]
    bot.reverse()
    return top, bot

def generate_market_review(indices, k200_top, k200_bot, k150_top, k150_bot):
    """실시간 뉴스 헤드라인 기반 마감 요약 리뷰 생성"""
    kospi = next((x for x in indices if "코스피 (KOSPI)" in x["name"]), {})
    kosdaq = next((x for x in indices if "코스닥 (KOSDAQ)" in x["name"]), {})
    fx = next((x for x in indices if "환율" in x["name"]), {})

    k_dir = "상승" if kospi.get("is_up") else ("하락" if kospi.get("is_down") else "보합")
    kq_dir = "상승" if kosdaq.get("is_up") else ("하락" if kosdaq.get("is_down") else "보합")

    fx_text = ""
    if fx.get("is_down"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 하향 안정화되며 외국인 수급 여건을 지지했습니다."
    elif fx.get("is_up"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 상승세를 보이며 대형 수출주에 영향을 미쳤습니다."
    else:
        fx_text = f"원·달러 환율은 <b>{fx.get('value')}</b> 선에서 보합권 흐름을 나타냈습니다."

    news_bullets = ""
    target_sectors = [(k200_top[0], "🔴", "코스피 상승 주도"), (k150_top[0], "🔴", "코스닥 상승 주도")]
    if k200_bot:
        target_sectors.append((k200_bot[0], "🔵", "코스피 하락 섹터"))
    
    for s, icon, label in target_sectors:
        n_text = ""
        if s.get("news"):
            first_n = s["news"][0]
            n_text = f'<a href="{first_n["link"]}" target="_blank" class="news-link">"{first_n["title"]}"</a> <span class="press-badge">{first_n["press"]}</span>'
        else:
            n_text = f"{s['lead_stock']} 등 주력 종목 중심의 수급 공방 지속"
        news_bullets += f"""
        <div class="review-item">
            <span class="bullet">{icon}</span>
            <div><b>[{label}: {s['name']} | {s['rate']:+}%]</b> {news_bullets_title_clean(n_text)}</div>
        </div>
        """

    review_html = f"""
    <div class="review-card">
        <div class="review-header">
            <span class="review-title">📝 정규장 마감 핵심 요약 & 실시간 언론사 뉴스 헤드라인</span>
            <span class="review-tag">네이버 금융 공식 뉴스 연동</span>
        </div>
        <div class="review-body">
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[마감 총평]</b> 코스피는 <b>{kospi.get('value')}</b>({k_dir}), 코스닥은 <b>{kosdaq.get('value')}</b>({kq_dir})으로 정규장을 마감했습니다.</div>
            </div>
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[환율 여건]</b> {fx_text}</div>
            </div>
            <div class="review-divider"></div>
            <div style="font-weight: 700; color: #1e293b; margin-bottom: 4px;">📰 당일 주요 섹터별 언론사 보도 헤드라인</div>
            {news_bullets}
        </div>
    </div>
    """
    return review_html

def news_bullets_title_clean(text):
    return text.replace("포토", "").replace("종합", "").strip()

def render_html(indices, k200_top, k200_bot, k150_top, k150_bot):
    kst_now = datetime.now(timezone(timedelta(hours=9)))
    now_str = kst_now.strftime("%Y년 %m월 %d일 15:30 정규장 마감 기준")
    
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
            
            # 실시간 뉴스 헤드라인 태그 생성
            news_tags = ""
            if s.get("news"):
                for n in s["news"][:1]:
                    news_tags += f"""<div class="sector-news">📰 <a href="{n['link']}" target="_blank" class="news-link">{n['title']}</a> <span class="press-badge">{n['press']}</span></div>"""
            else:
                news_tags = f"""<div class="sector-news" style="color: #94a3b8;">당일 집계된 관련 특징주 뉴스가 없습니다.</div>"""

            html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{sign}{s['rate']}%</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
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
    <title>국내 정규장 마감 대시보드</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
        body {{ background-color: #f4f6f9; color: #1e293b; padding: 16px; max-width: 960px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 20px; }}
        h1 {{ font-size: 1.45rem; font-weight: 800; color: #0f172a; margin-bottom: 4px; }}
        .timestamp {{ font-size: 0.88rem; font-weight: 600; color: #475569; }}
        
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 22px; }}
        .card {{ background: #fff; padding: 16px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.82rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.28rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .badge {{ display: inline-block; font-size: 0.78rem; font-weight: 700; padding: 3px 10px; border-radius: 6px; }}
        
        /* 마감 리뷰 브리핑 박스 */
        .review-card {{ background: #ffffff; border-radius: 12px; border-left: 5px solid #2563eb; border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; padding: 18px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
        .review-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 10px; }}
        .review-title {{ font-size: 1.08rem; font-weight: 800; color: #0f172a; }}
        .review-tag {{ font-size: 0.75rem; font-weight: 700; color: #1d4ed8; background: #dbeafe; padding: 3px 8px; border-radius: 6px; }}
        .review-body {{ display: flex; flex-direction: column; gap: 9px; font-size: 0.92rem; line-height: 1.6; color: #334155; }}
        .review-item {{ display: flex; align-items: flex-start; gap: 8px; }}
        .bullet {{ font-size: 0.95rem; line-height: 1.4; }}
        .review-divider {{ height: 1px; background: #e2e8f0; margin: 4px 0; }}
        
        .news-link {{ color: #0f172a; text-decoration: none; font-weight: 600; transition: color 0.2s; }}
        .news-link:hover {{ color: #2563eb; text-decoration: underline; }}
        .press-badge {{ font-size: 0.72rem; color: #64748b; background: #f1f5f9; border: 1px solid #e2e8f0; padding: 2px 6px; border-radius: 4px; margin-left: 4px; font-weight: 500; }}

        .group-title {{ font-size: 1.15rem; font-weight: 800; margin: 26px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #cbd5e1; color: #0f172a; }}
        .section-title {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 16px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .sector-item {{ padding: 12px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-item:last-child {{ border-bottom: none; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .sector-name {{ font-weight: 700; font-size: 0.98rem; }}
        .sector-rate {{ font-weight: 800; font-size: 0.98rem; }}
        
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 3px 8px; font-size: 0.82rem; }}
        .sector-news {{ font-size: 0.84rem; color: #475569; background: #f8fafc; padding: 7px 10px; border-radius: 6px; border-left: 3px solid #3b82f6; }}
        
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
