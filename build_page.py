import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import requests
import google.generativeai as genai

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
}

DASHBOARD_URL = "https://rmadh6418-ai.github.io/stock-dashboard/"

# --- Gemini API 설정 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-pro')
else:
    gemini_model = None
    print("[WARNING] GEMINI_API_KEY가 설정되지 않아 기본 텍스트 생성 모드로 작동합니다.")

# 경제·기업과 무관한 뉴스 필터링용 제외 키워드 목록
EXCLUDE_NEWS_KEYWORDS = [
    "콘서트", "포크", "음악회", "축제", "페스티벌", "공연", "전시회", "문화", 
    "봉사", "기부", "나눔", "장학", "사회공헌", "바자회", "캠페인", "후원", 
    "부고", "부음", "화혼", "결혼", "인사", "동정", "알림", "모집", "채용", 
    "이벤트", "경품", "할인", "프로모션", "쿠폰", "체험단", "선착순", "추첨", 
    "골프대회", "마라톤", "시상식", "장학금", "헌혈", "가을", "여행", "맛집", 
    "포토", "영상", "방송", "예능",
]

BUSINESS_NEWS_KEYWORDS = [
    "실적", "매출", "영업익", "영업이익", "순이익", "수주", "계약", "투자", 
    "공급", "인수", "합병", "M&A", "증설", "공시", "주가", "상승", "하락", 
    "급등", "급락", "수출", "양산", "출시", "기술", "개발", "협력", "제휴", 
    "공장", "가동", "수혜", "흑자", "적자", "전망", "목표가", "배당", "지분", 
    "증자", "특허", "사업", "성장", "솔루션", "생산", "상장", "신제품", "AI", 
    "반도체", "배터리", "로봇", "방산", "원전", "바이오", "임상", "승인", 
    "신약", "수주잔고", "체결", "공급계약",
]

SECTOR_MOMENTUM_THEMES = {
    "화학·에너지": "국제 유가 변동 및 정제마진, 석유화학 업황",
    "이차전지·배터리": "글로벌 전기차 수요 및 배터리 셀·소재 수급",
    "조선·중공업": "고부가가치 선박 수주 및 신조선가 상승 추세",
    "전기·전자 (반도체/IT)": "AI 인프라 투자 및 차세대 반도체·부품 수요",
    "자동차·운송장비": "완성차 글로벌 판매 실적 및 전동화 비중",
    "원전·전력인프라": "AI 전력망 증설 및 글로벌 전력기기·원전 수요",
    "방위산업·우주항공": "K-방산 글로벌 수출 수주 호조 및 안보 수요",
    "제약·바이오": "신약 파이프라인 성과 및 글로벌 기술수출 기대감",
    "금융·지주": "주주환원 정책(밸류업) 및 금리 환경",
    "인터넷·플랫폼": "AI 신규 서비스 수익화 및 플랫폼 실적",
    "건설·시공": "국내외 인프라 수주 및 부동산 PF 환경",
    "철강·금속": "원자재 가격 및 글로벌 철강·비철금속 수요",
    "음식료·유통": "K-푸드 글로벌 수출 성장세 및 원가율 개선",
    "이차전지·소재": "양극재·음극재 등 핵심 소재 수급 및 판가 추이",
    "반도체 소부장": "차세대 패키징 및 반도체 공정 장비·소재 납품",
    "엔터·미디어": "소속 아티스트 글로벌 활동 및 콘텐츠 음원 매출",
    "게임·소프트웨어": "신작 출시 성과 및 글로벌 플랫폼 확장",
    "로봇·자동화": "산업용 로봇 및 스마트팩토리 자동화 수요",
    "피팅·배관기자재": "조선·해양플랜트 및 EPC 배관 기자재 수주",
}

def get_json(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url, safe='')}"
        res = requests.get(proxy_url, timeout=8)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def get_html(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            return res.content.decode("euc-kr", "replace")
    except Exception:
        pass
    try:
        proxy_url = f"https://api.allorigins.win/raw?url={urllib.parse.quote(url, safe='')}"
        res = requests.get(proxy_url, timeout=10)
        if res.status_code == 200:
            return res.content.decode("euc-kr", "replace")
    except Exception:
        pass
    return ""


def generate_gemini_summary(sec_name, rate, matched_stocks):
    if not gemini_model:
        return f"{sec_name} 섹터는 주요 종목 간 수급 공방이 이어지며 {rate:+.2f}%를 기록했습니다."

    if not matched_stocks:
        return f"{sec_name} 섹터 관련 유의미한 종목 데이터가 부족합니다."

    parts = []
    for s in matched_stocks[:3]:
        sign = "+" if s["rate"] > 0 else ""
        parts.append(f"{s['name']}({sign}{s['rate']:.2f}%)")
    stock_str = ", ".join(parts)
    theme = SECTOR_MOMENTUM_THEMES.get(sec_name, "해당 업종 시장 수급 이슈")

    prompt = (
        f"당신은 날카롭고 객관적인 주식/경제 분석가입니다. 오늘 국내 증시에서 '{sec_name}' 섹터의 "
        f"평균 등락률은 {rate:+.2f}%를 기록했으며, 주요 상승/하락 주도 종목은 {stock_str} 입니다. "
        f"이 섹터의 주요 모멘텀은 '{theme}' 입니다. "
        f"이 데이터들을 바탕으로 오늘 해당 섹터가 왜 이런 흐름을 보였는지, 시장의 핵심 원인과 투심을 "
        f"단 2문장으로 압축해서 전문적인 리포트 어조로 설명해 주세요. 종목 추천은 하지 마세요."
    )

    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[ERROR] Gemini API Error: {e}")
        return f"{sec_name} 섹터는 {stock_str} 등을 중심으로 {rate:+.2f}%의 변동성을 보였습니다."


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

    if not has_stock and not has_biz:
        return -1

    return score


def fetch_real_news(keyword, stock_code=""):
    candidates = []
    if stock_code:
        url = f"https://finance.naver.com/item/news_news.naver?code={stock_code}&page=1"
        html = get_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
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
                            link = "https://finance.naver.com" + a_tag["href"]
                            press = td_info.text.strip() if td_info else "증권뉴스"
                            candidates.append({
                                "title": raw_title, "press": press, "link": link, "score": score,
                            })
                            if len(candidates) >= 5:
                                break

    if len(candidates) < 2:
        enc_query = urllib.parse.quote(f"{keyword} 특징주", encoding="euc-kr")
        url = f"https://finance.naver.com/news/news_search.naver?q={enc_query}"
        html = get_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            dl_list = soup.find_all("dl", class_="articleList") or soup.find_all("dl")
            for dl in dl_list:
                dt = dl.find("dd", class_="articleSubject") or dl.find("dt")
                if dt and dt.find("a"):
                    a_tag = dt.find("a")
                    raw_title = a_tag.text.strip()
                    score = get_news_score(raw_title, keyword)
                    if score > 0:
                        link = "https://finance.naver.com" + a_tag["href"]
                        summary = dl.find("dd", class_="articleSummary")
                        press = (
                            summary.find("span", class_="press").text.strip()
                            if summary and summary.find("span", class_="press") else "증권뉴스"
                        )
                        candidates.append({
                            "title": raw_title, "press": press, "link": link, "score": score,
                        })
                        if len(candidates) >= 4:
                            break

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:2]


# 💡 뻗지 않도록 4중 철벽 안전장치를 추가했습니다!
def get_world_market_index(name, code_key, marketindexCd, unit=""):
    url = f"https://finance.naver.com/marketindex/worldDailyQuote.naver?marketindexCd={marketindexCd}"
    html = get_html(url)
    if html:
        soup = BeautifulSoup(html, "html.parser")
        table = soup.find("table", class_="tbl_exchange")
        if table:
            tbody = table.find("tbody")
            if tbody:
                tr = tbody.find("tr")
                if tr:
                    tds = tr.find_all("td")
                    if len(tds) >= 4:
                        val = tds[0].text.strip()
                        diff = tds[2].text.strip()
                        rate = tds[3].text.strip()
                        
                        is_up = "상승" in str(tds[2])
                        is_down = "하락" in str(tds[2])
                        
                        return {
                            "name": name,
                            "code_key": code_key,
                            "value": f"{val}{unit}",
                            "change_val": diff,
                            "change_rate": float(rate.replace("%", "")) if rate != "-" else 0.0,
                            "is_up": is_up,
                            "is_down": is_down,
                        }
        
    return {
        "name": name, "code_key": code_key, "value": "-", 
        "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False
    }


def get_investor_trend():
    trends = {"KOSPI": "집계 중...", "KOSDAQ": "집계 중..."}
    targets = [("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")]
    
    for name, code in targets:
        url = f"https://finance.naver.com/sise/sise_index.naver?code={code}"
        html = get_html(url)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            dl = soup.find("dl", class_="lst_kos_info")
            if dl:
                dds = dl.find_all("dd")
                parts = []
                for dd in dds:
                    text = dd.text.strip()
                    if text.startswith("개인") or text.startswith("외국인") or text.startswith("기관"):
                        entity = text.split(" ")[0]
                        val_str = text.replace(entity, "").strip()
                        
                        color = "text-down" if "-" in val_str else "text-up"
                        sign = "" if "-" in val_str else "+"
                        
                        parts.append(f"{entity} <span class='{color} font-bold'>{sign}{val_str}</span>")
                
                if parts:
                    trends[name] = " | ".join(parts)
            
    return trends


def get_exchange_rate():
    data = get_json("https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=FRX.KRWUSD")
    if data and len(data) > 0:
        item = data[0]
        price = f"{item['basePrice']:,.2f}원"
        diff = f"{item['changePrice']:,.2f}"
        rate = round(item.get("changeRate", 0) * 100, 2)
        chg = item.get("change", "EVEN")
        is_up = chg == "RISE"
        is_down = chg == "FALL"
        return {
            "name": "원·달러 환율", "code_key": "FX_USDKRW", "value": price,
            "change_val": diff, "change_rate": rate, "is_up": is_up, "is_down": is_down,
        }
    
    return {
        "name": "원·달러 환율", "code_key": "FX_USDKRW", "value": "-", 
        "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False,
    }


def get_market_indices():
    targets = [
        ("코스피", "KOSPI", "https://m.stock.naver.com/api/index/KOSPI/basic"),
        ("코스닥", "KOSDAQ", "https://m.stock.naver.com/api/index/KOSDAQ/basic"),
        ("코스피 200", "KPI200", "https://m.stock.naver.com/api/index/KPI200/basic"),
    ]
    results = []
    for name, key, url in targets:
        data = get_json(url)
        if data:
            val = data.get("closePrice", "-")
            diff = data.get("compareToPreviousClosePrice", "0")
            try:
                rate = abs(float(data.get("fluctuationsRatio", 0)))
            except Exception:
                rate = 0.0

            cd = str(data.get("compareToPreviousPrice", {}).get("code", "3"))
            is_up = cd in ["1", "2"]
            is_down = cd in ["4", "5"]

            results.append({
                "name": name, "code_key": key, "value": val, "change_val": diff,
                "change_rate": rate, "is_up": is_up, "is_down": is_down,
            })
        else:
            results.append({
                "name": name, "code_key": key, "value": "-", "change_val": "0",
                "change_rate": 0.0, "is_up": False, "is_down": False,
            })

    results.append(get_exchange_rate())
    results.append(get_world_market_index("미국채 10년물", "US_10Y", "IR_TNX", "%"))
    results.append(get_world_market_index("미국채 30년물", "US_30Y", "IR_TYX", "%"))
    results.append(get_world_market_index("금값(Gold)", "COM_GOLD", "CMDT_GC", "$"))
    results.append(get_world_market_index("엔·달러 환율", "FX_USDJPY", "FX_USDJPY", "엔"))
    
    return results


def get_market_stocks():
    stocks = {}
    for market in ["KOSPI", "KOSDAQ"]:
        for page in [1, 2, 3]:
            url = f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=200"
            data = get_json(url)
            if data and "stocks" in data:
                for item in data["stocks"]:
                    name = item.get("stockName")
                    code = item.get("itemCode")
                    price = item.get("closePrice", "0")
                    rate = float(item.get("fluctuationsRatio", 0))
                    stocks[name] = {
                        "price": price, "rate": rate, "code": code, "market": market
                    }
    return stocks


KOSPI200_SECTORS = {
    "화학·에너지": ["LG화학", "S-Oil", "SK이노베이션", "롯데케미칼", "SK가스", "GS", "한국가스공사"],
    "이차전지·배터리": ["LG에너지솔루션", "POSCO홀딩스", "포스코퓨처엠", "삼성SDI", "엘앤에프", "에코프로머티", "코스모신소재"],
    "조선·중공업": ["HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양", "한화엔진", "HD현대", "HD현대마린솔루션"],
    "전기·전자 (반도체/IT)": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "한미반도체", "LG전자", "이수페타시스"],
    "자동차·운송장비": ["현대차", "기아", "현대모비스", "현대오토에버", "현대글로비스", "현대위아"],
    "원전·전력인프라": ["한국전력", "두산에너빌리티", "한전기술", "한전KPS", "효성중공업", "LS ELECTRIC", "HD현대일렉트릭"],
    "방위산업·우주항공": ["한화에어로스페이스", "현대로템", "한국항공우주", "한화시스템", "LIG넥스원"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "유한양행", "한미약품", "SK바이오팜", "삼성에피스홀딩스", "대웅제약"],
    "금융·지주": ["KB금융", "신한지주", "하나금융지주", "메리츠금융지주", "기업은행", "미래에셋증권", "삼성증권"],
    "인터넷·플랫폼": ["NAVER", "카카오", "크래프톤"],
    "건설·시공": ["현대건설", "대우건설", "GS건설", "DL이앤씨"],
    "철강·금속": ["고려아연", "현대제철", "동국제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심"],
}

KOSDAQ150_SECTORS = {
    "제약·바이오": ["알테오젠", "HLB", "삼천당제약", "리가켐바이오", "휴젤", "에스티팜", "HK이노엔", "펩트론"],
    "이차전지·소재": ["에코프로비엠", "에코프로", "엔켐", "대주전자재료", "서진시스템", "나노신소재", "피엔티"],
    "반도체 소부장": ["HPSP", "리노공업", "주성엔지니어링", "이오테크닉스", "솔브레인", "동진쎄미켐", "ISC", "대덕전자"],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드"],
    "로봇·자동화": ["레인보우로보틱스", "로보티즈", "에스에프에이", "휴림로봇", "유일로보틱스"],
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
                matched.append({
                    "name": sname, "rate": item["rate"], "price": item["price"], "code": item.get("code", ""),
                })
                rates.append(item["rate"])
        if matched:
            matched.sort(key=lambda x: abs(x["rate"]), reverse=True)
            top_stock_name = matched[0]["name"]
            top_stock_code = matched[0].get("code", "")
            news_items = fetch_real_news(top_stock_name, top_stock_code)
            avg_r = sum(rates) / len(rates)
            
            summary_text = generate_gemini_summary(sec_name, avg_r, matched)
            
            results.append({
                "name": sec_name, "rate": round(avg_r, 2), "stocks": matched[:3],
                "lead_stock": top_stock_name, "summary": summary_text, "news": news_items,
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

    fx_text = ""
    if fx.get("is_down"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 하향 안정화되며 수급 여건을 지지했습니다."
    elif fx.get("is_up"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 상승세를 보이며 대형 수출주에 영향을 미쳤습니다."
    else:
        fx_text = f"원·달러 환율은 <b>{fx.get('value')}</b> 선에서 보합권 흐름을 나타냈습니다."

    target_sectors = []
    if k200_top:
        target_sectors.append((k200_top[0], "🔴", "코스피 상승 주도" if k200_top[0]["rate"] > 0 else "코스피 방어"))
    if k150_top:
        target_sectors.append((k150_top[0], "🔴", "코스닥 상승 주도" if k150_top[0]["rate"] > 0 else "코스닥 방어"))
    if k200_bot:
        target_sectors.append((k200_bot[0], "🔵", "코스피 낙폭 과대 섹터"))

    news_bullets = ""
    for s, icon, label in target_sectors:
        n_text = ""
        if s.get("news"):
            first_n = s["news"][0]
            clean_t = first_n["title"].replace('"', "&quot;")
            n_text = f'<a href="{first_n["link"]}" target="_blank" class="news-link">"{clean_t}"</a> <span class="press-badge">{first_n["press"]}</span>'
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
            <div style="font-weight: 700; color: #1e293b; margin-bottom: 4px;">📰 당일 주요 섹터별 언론사 보도 헤드라인 (경제·기업 핵심 뉴스)</div>
            {news_bullets}
        </div>
    </div>
    """
    return review_html


def render_html(indices, investor_data, k200_top, k200_bot, k150_top, k150_bot):
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

        rate_text = f"{sign}{abs(idx['change_rate']):.2f}%" if idx["change_rate"] != 0.0 else f"{sign}0.00%"
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
            return '<div class="sector-item" style="color:#64748b;">데이터 통신 지연으로 집계를 완료하지 못했습니다. 잠시 후 새로고침 해주세요.</div>'

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
                st_color = "text-up" if st_r > 0 else ("text-down" if st_r < 0 else "text-flat")
                st_sign = "+" if st_r > 0 else ("-" if st_r < 0 else "")
                code_attr = f'data-stock-code="{st.get("code", "")}"' if st.get("code") else ""
                stock_tags += f"""
                <span class="stock-pill" {code_attr}>
                    <span class="stock-name">{st['name']}</span> 
                    <b class="stock-rate {st_color}">{st_sign}{abs(st_r):.2f}%</b>
                    <span class="stock-price">({st['price']}원)</span>
                </span>"""

            summary_html = f'<div class="sector-summary"><span class="summary-badge">🤖 AI 분석</span> {s.get("summary", "")}</div>' if s.get("summary") else ""
            
            news_tags = ""
            if s.get("news"):
                for n in s["news"][:1]:
                    news_tags += f"""<div class="sector-news">📰 <a href="{n['link']}" target="_blank" class="news-link">{n['title']}</a> <span class="press-badge">{n['press']}</span></div>"""
            else:
                news_tags = """<div class="sector-news" style="color: #94a3b8;">당일 집계된 관련 기업/경제 뉴스가 없습니다.</div>"""

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
    <title>실시간 국내 증시 대시보드</title>
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
        
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 12px; }}
        .card {{ background: #fff; padding: 16px 12px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.82rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.30rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; transition: color 0.3s; }}
        .badge {{ display: inline-block; font-size: 0.78rem; font-weight: 700; padding: 3px 10px; border-radius: 6px; }}
        
        .investor-card {{ background: #fff; padding: 14px 18px; border-radius: 12px; border: 1px solid #e2e8f0; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); font-size: 0.88rem; }}
        .investor-title {{ font-weight: 800; color: #0f172a; margin-bottom: 8px; font-size: 0.95rem; border-bottom: 1px solid #f1f5f9; padding-bottom: 6px; }}
        .investor-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 4px; color: #334155; }}
        .investor-row b {{ min-width: 80px; }}

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
        .sector-name {{ font-weight: 800; font-size: 1.02rem; color: #0f172a; }}
        .sector-rate {{ font-weight: 800; font-size: 0.98rem; }}
        
        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 9px; font-size: 0.82rem; }}
        .stock-price {{ color: #64748b; font-size: 0.78rem; margin-left: 3px; }}
        
        .sector-summary {{ font-size: 0.86rem; line-height: 1.55; color: #334155; background: #f1f5f9; border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; border-left: 3px solid #8b5cf6; }}
        .summary-badge {{ font-weight: 800; color: #6d28d9; display: inline-block; margin-right: 4px; }}
        .sector-news {{ font-size: 0.84rem; color: #475569; background: #f8fafc; padding: 7px 10px; border-radius: 6px; border-left: 3px solid #3b82f6; }}
        
        .font-bold {{ font-weight: 700; }}
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
        <h1>📊 실시간 국내 증시 대시보드</h1>
        <div class="status-bar">
            <span class="timestamp" id="live-clock">🕒 시간 계산 중...</span>
            <span class="live-status" id="market-status">동기화 확인 중</span>
        </div>
    </header>

    <div class="grid-indices">
        {index_cards}
    </div>
    
    <div class="investor-card">
        <div class="investor-title">🤝 투자자별 매매동향 (잠정)</div>
        <div class="investor-row"><b>코스피</b> <span>{investor_data['KOSPI']}</span></div>
        <div class="investor-row"><b>코스닥</b> <span>{investor_data['KOSDAQ']}</span></div>
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
        function updateLiveClock() {{
            const now = new Date();
            const kstFormatter = new Intl.DateTimeFormat('ko-KR', {{
                timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', 
                weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
            }});
            const clockEl = document.getElementById('live-clock');
            if (clockEl) clockEl.textContent = '🕒 ' + kstFormatter.format(now) + ' (KST)';

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
                    statusEl.textContent = '🔴 실시간 장중 연동 중';
                }} else {{
                    statusEl.className = 'live-status status-closed';
                    statusEl.textContent = '🏁 정규장 마감 확정';
                }}
            }}
        }}
        setInterval(updateLiveClock, 1000);
        updateLiveClock();
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
        token_url = "https://kauth.kakao.com/oauth/token"
        token_data = {
            "grant_type": "refresh_token",
            "client_id": rest_api_key,
            "refresh_token": refresh_token,
        }
        t_res = requests.post(token_url, data=token_data, timeout=5).json()
        access_token = t_res.get("access_token")

        if not access_token:
            return

        kst_now = datetime.now(timezone(timedelta(hours=9)))
        date_str = kst_now.strftime("%m/%d 15:30 마감")

        kospi = next((x for x in indices if "코스피" in x["name"]), {})
        kosdaq = next((x for x in indices if "코스닥" in x["name"]), {})
        fx = next((x for x in indices if "환율" in x["name"]), {})

        k_sign = "▲ +" if kospi.get("is_up") else ("▼ -" if kospi.get("is_down") else "")
        kq_sign = "▲ +" if kosdaq.get("is_up") else ("▼ -" if kosdaq.get("is_down") else "")
        fx_sign = "▲ +" if fx.get("is_up") else ("▼ -" if fx.get("is_down") else "")

        k200_lead = k200_top[0]["name"] if k200_top else "집계중"
        k150_lead = k150_top[0]["name"] if k150_top else "집계중"

        msg_text = (
            f"📊 [정규장 마감 리포트] {date_str}\n\n"
            f"• 코스피: {kospi.get('value')} ({k_sign}{abs(kospi.get('change_rate', 0)):.2f}%, {kospi.get('change_val')})\n"
            f"• 코스닥: {kosdaq.get('value')} ({kq_sign}{abs(kosdaq.get('change_rate', 0)):.2f}%, {kosdaq.get('change_val')})\n"
            f"• 원·달러: {fx.get('value')} ({fx_sign}{abs(fx.get('change_rate', 0)):.2f}%)\n"
            f"• 상대강세: {k200_lead} / {k150_lead}\n\n"
            f"대시보드 접속 시 전체 섹터별 Gemini AI 분석 요약을 확인하실 수 있습니다."
        )

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
                "button_title": "📊 AI 대시보드 바로가기",
            })
        }
        requests.post(send_url, headers=headers, data=payload, timeout=5)
    except Exception:
        pass


if __name__ == "__main__":
    indices = get_market_indices()
    investor_data = get_investor_trend() 
    stock_data = get_market_stocks()
    k200_top, k200_bot = calculate_sectors(KOSPI200_SECTORS, stock_data)
    k150_top, k150_bot = calculate_sectors(KOSDAQ150_SECTORS, stock_data)

    render_html(indices, investor_data, k200_top, k200_bot, k150_top, k150_bot)
    send_kakao_alert(indices, k200_top, k150_top)
