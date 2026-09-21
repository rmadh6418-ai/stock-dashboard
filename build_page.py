import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
import requests
import google.generativeai as genai

def get_headers(is_daum=False):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if is_daum:
        headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        headers["Referer"] = "https://finance.daum.net/"
    else:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        headers["Referer"] = "https://finance.naver.com/"
    return headers

DASHBOARD_URL = "https://rmadh6418-ai.github.io/stock-dashboard/"

# Gemini API 초기화
API_KEY = os.environ.get("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

EXCLUDE_NEWS_KEYWORDS = ["콘서트", "포크", "음악회", "축제", "페스티벌", "공연", "전시회", "문화", "봉사", "기부", "나눔", "장학", "사회공헌", "바자회", "캠페인", "후원", "부고", "부음", "화혼", "결혼", "인사", "동정", "알림", "모집", "채용", "이벤트", "경품", "할인", "프로모션", "쿠폰", "체험단", "선착순", "추첨", "골프대회", "마라톤", "시상식", "장학금", "헌혈", "가을", "여행", "맛집"]
BUSINESS_NEWS_KEYWORDS = ["실적", "매출", "영업익", "영업이익", "순이익", "수주", "계약", "투자", "공급", "인수", "합병", "M&A", "증설", "공시", "주가", "상승", "하락", "급등", "급락", "수출", "양산", "출시", "기술", "개발", "협력", "제휴", "공장", "가동", "수혜", "흑자", "적자", "전망", "목표가", "배당", "지분", "증자", "특허", "사업", "성장", "솔루션", "생산", "상장", "신제품", "AI", "반도체", "배터리", "로봇", "방산", "원전", "바이오", "임상", "승인", "신약", "수주잔고", "체결", "공급계약"]

KOSPI200_SECTORS = {
    "화학·에너지": ["LG화학", "S-Oil", "SK이노베이션", "롯데케미칼", "SK가스", "GS", "한국가스공사", "한화솔루션", "금호석유", "OCI홀딩스", "대한유화"],
    "이차전지·배터리": ["LG에너지솔루션", "POSCO홀딩스", "포스코퓨처엠", "삼성SDI", "엘앤에프", "에코프로머티", "코스모신소재", "포스코인터내셔널", "솔루스첨단소재", "금양"],
    "조선·해운·중공업": ["HD현대중공업", "한화오션", "삼성중공업", "HD한국조선해양", "한화엔진", "HD현대", "HD현대마린엔진", "HD현대마린솔루션", "대한조선", "한국카본", "HD현대미포", "HMM", "팬오션"],
    "전기·전자 (반도체/IT)": ["삼성전자", "SK하이닉스", "삼성전기", "LG이노텍", "한미반도체", "LG전자", "이수페타시스", "DB하이텍", "삼성에스디에스", "LG디스플레이", "해성디에스"],
    "자동차·운송장비": ["현대차", "기아", "현대모비스", "현대오토에버", "현대글로비스", "현대위아", "에스엘", "HL만도", "한국타이어앤테크놀로지"],
    "원전·전력인프라": ["한국전력", "두산에너빌리티", "한전기술", "한전KPS", "효성중공업", "산일전기", "대한전선", "일진전기", "LS ELECTRIC", "HD현대일렉트릭", "LS에코에너지", "LS", "효성"],
    "방위산업·우주항공": ["한화에어로스페이스", "현대로템", "한국항공우주", "한화시스템", "LIG넥스원", "한화", "풍산"],
    "제약·바이오": ["삼성바이오로직스", "셀트리온", "유한양행", "한미약품", "SK바이오팜", "삼성에피스홀딩스", "녹십자", "대웅제약", "SK바이오사이언스", "종근당", "대원제약", "한올바이오파마"],
    "화장품·의류": ["아모레퍼시픽", "LG생활건강", "한국콜마", "코스맥스", "토니모리", "애경산업", "F&F", "영원무역"],
    "금융·지주": ["KB금융", "신한지주", "하나금융지주", "메리츠금융지주", "기업은행", "우리금융지주", "IM금융지주", "카카오뱅크", "카카오페이", "삼성물산", "SK"],
    "손해보험": ["삼성화재", "DB손해보험", "현대해상", "한화손해보험", "삼성화재우", "롯데손해보험", "서울보증보험", "삼성생명", "코리안리"],
    "증권사": ["삼성증권", "미래에셋증권", "한국금융지주", "키움증권", "SK증권", "NH투자증권", "한화투자증권", "현대차증권", "대신증권"],
    "인터넷·게임·플랫폼": ["NAVER", "카카오", "크래프톤", "엔씨소프트", "넷마블"],
    "건설·시공": ["현대건설", "대우건설", "GS건설", "DL이앤씨", "HDC현대산업개발"],
    "철강·금속": ["고려아연", "현대제철", "동국제강", "세아제강"],
    "음식료·유통": ["삼양식품", "CJ제일제당", "오리온", "농심", "BGF리테일", "이마트", "롯데쇼핑", "신세계", "하이트진로"],
}

KOSDAQ150_SECTORS = {
    "제약·바이오": ["알테오젠", "HLB", "삼천당제약", "리가켐바이오", "에스티팜", "HK이노엔", "동국제약", "지투지바이오", "디엔디파마텍", "올릭스", "에이비엘바이오", "펩트론", "오스코텍", "엘앤씨바이오", "셀트리온제약", "차바이오텍", "메디톡스", "보로노이", "지노믹트리"],
    "미용의료·화장품": ["휴젤", "클래시스", "실리콘투", "파마리서치", "제이시스메디칼", "원텍", "브이티", "아이패밀리에스씨", "마녀공장", "코스메카코리아"],
    "이차전지·소재": ["에코프로비엠", "에코프로", "엔켐", "대주전자재료", "서진시스템", "나노신소재", "피엔티", "동화기업", "한중엔시에스", "에코프로에이치엔", "성일하이텍", "더블유씨피", "윤성에프앤씨", "새빗켐"],
    "반도체 소부장": ["HPSP", "리노공업", "주성엔지니어링", "이오테크닉스", "솔브레인", "동진쎄미켐", "티씨케이", "ISC", "하나머티리얼즈", "대덕전자", "유진테크", "심텍", "원익IPS", "테크윙", "파크시스템스", "두산테스나", "필옵틱스", "씨엠티엑스", "원익QnC", "고영", "이녹스첨단소재", "에프에스티", "동운아나텍", "넥스틴", "가온칩스"],
    "엔터·미디어": ["JYP Ent.", "에스엠", "스튜디오드래곤", "CJ ENM", "와이지엔터테인먼트", "디어유", "초록뱀미디어", "삼화네트웍스"],
    "게임·소프트웨어": ["펄어비스", "카카오게임즈", "위메이드", "넥슨게임즈", "컴투스", "네오위즈", "웹젠", "엠게임", "안랩"],
    "로봇·자동화": ["레인보우로보틱스", "로보티즈", "에스에프에이", "휴림로봇", "로보스타", "에스피지", "하이젠알앤엠", "삼현", "유일로보틱스", "티로보틱스", "에브리봇", "뉴로메카", "알에스오토메이션"],
    "피팅·배관기자재": ["성광벤드", "태광", "하이록코리아", "디케이락", "비엠티", "태웅"],
}

# 라이브 서버에서 기존 AI 텍스트 긁어오기 (에러 방어용)
# 💡 아래 2개의 함수만 기존 코드에 덮어씌우시면 됩니다.

def get_live_ai_summary():
    try:
        res = requests.get(f"{DASHBOARD_URL}?t={int(time.time())}", timeout=3)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            ai_div = soup.find("div", class_="market-ai-content")
            if ai_div:
                text = ai_div.get_text(strip=True)
                # 💡 핵심 수정 1: 라이브 사이트에 떠 있는 글이 '에러'나 '[요약]' 텍스트라면 복사하지 않고 무시합니다.
                if not text.startswith("🚨") and not text.startswith("💡") and not text.startswith("[요약]"):
                    return ai_div.decode_contents() + " <span style='font-size:0.8em; color:#94a3b8; margin-left:6px;'>(이전 분석 유지)</span>"
    except: pass
    return None

def generate_ai_market_summary(indices, k200_top, k200_bot, k150_top, k150_bot):
    kospi = next((x for x in indices if "코스피 (KOSPI)" in x["name"]), {})
    kosdaq = next((x for x in indices if "코스닥 (KOSDAQ)" in x["name"]), {})

    k200_strong = ", ".join([s['name'] for s in k200_top]) if k200_top else "특이사항 없음"
    k150_strong = ", ".join([s['name'] for s in k150_top]) if k150_top else "특이사항 없음"
    
    fallback_text = (
        f"[요약] 코스피({kospi.get('value')})와 코스닥({kosdaq.get('value')})은 오늘 "
        f"{k200_strong} 및 {k150_strong} 섹터를 중심으로 변동성을 보였습니다."
    )

    if not API_KEY or API_KEY.strip() == "":
        return f"💡 API 키가 등록되지 않았습니다.<br><br>{fallback_text}"

    os.makedirs("public", exist_ok=True)
    cache_file = "public/ai_summary_cache.json"
    cache_url = f"{DASHBOARD_URL.rstrip('/')}/ai_summary_cache.json"
    cache_duration = 1800

    # 1. 라이브 웹페이지에서 기존 캐시 원격 다운로드
    try:
        res = requests.get(f"{cache_url}?t={int(time.time())}", timeout=3)
        if res.status_code == 200:
            cache_data = res.json()
            # 💡 [요약]으로 시작하는 잘못된 캐시는 버리도록 조건 추가
            if time.time() - cache_data.get("timestamp", 0) < cache_duration and not cache_data.get("text", "").startswith("[요약]"):
                print("[INFO] 라이브 서버에서 30분 이내의 정상적인 AI 분석 캐시를 불러옵니다.")
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(cache_data, f, ensure_ascii=False)
                return cache_data.get("text")
    except Exception as e:
        print(f"[WARN] 원격 캐시 파일 읽기 오류: {e}")

    # 2. 로컬 캐시 확인
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
                if time.time() - cache_data.get("timestamp", 0) < cache_duration and not cache_data.get("text", "").startswith("[요약]"):
                    return cache_data.get("text")
        except: pass

    prompt = f"""
    당신은 대한민국 상위 1% 전문 펀드매니저이자 날카로운 시각을 가진 주식시장 분석가입니다.
    오늘의 한국 주식시장(코스피, 코스닥) 데이터를 바탕으로 전체 시황을 아주 상세하게 분석해주세요.

    [오늘의 핵심 데이터]
    - 코스피 지수: {kospi.get('value')} (변동: {kospi.get('change_val')} / {kospi.get('change_rate')}%)
    - 코스닥 지수: {kosdaq.get('value')} (변동: {kosdaq.get('change_val')} / {kosdaq.get('change_rate')}%)
    - 코스피 상승 주도 섹터: {k200_strong}
    - 코스닥 상승 주도 섹터: {k150_strong}

    [작성 지침]
    1. 지수 등락과 주도 섹터의 흐름을 바탕으로 시장의 분위기를 깊이 있게 분석할 것.
    2. 주가 상황을 바탕으로 리스크가 무엇이 있을지 대비는 어떻게 해야하는지 분석할 것.
    3. 전체 분량은 4~6문장 분량으로 매끄러운 단일 평문으로 작성할 것.
    4. 마크다운 기호(*, # 등)는 일절 쓰지 말 것.
    """

    # 💡 핵심 수정 2: 모델 호출을 전담하는 내부 함수 (실패 시 무조건 작동하는 기본 모델로 자동 우회)
    def call_gemini():
        try:
            model = genai.GenerativeModel('gemini-3.6-flash')
            return model.generate_content(prompt)
        except Exception as ex:
            if "404" in str(ex) or "not found" in str(ex).lower():
                print("[INFO] 최신 모델 인식이 실패하여, 모든 환경에서 작동하는 기본 모델(gemini-pro)로 우회합니다.")
                fallback_model = genai.GenerativeModel('gemini-pro')
                return fallback_model.generate_content(prompt)
            raise ex

    try:
        response = call_gemini()
        if response and hasattr(response, 'text') and response.text:
            result_text = response.text.strip().replace('\n', ' ')
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": time.time(), "text": result_text}, f, ensure_ascii=False)
            except: pass
            return result_text
        else:
            return f"🚨 AI 응답 텍스트가 비어 있습니다.<br><br>{fallback_text}"
    except Exception as e:
        error_str = str(e)
        
        # 429 에러 발생 시 최후의 방어
        if "429" in error_str:
            live_text = get_live_ai_summary()
            if live_text:
                return live_text
            
            time.sleep(60)
            try:
                response = call_gemini()
                if response and hasattr(response, 'text') and response.text:
                    result_text = response.text.strip().replace('\n', ' ')
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump({"timestamp": time.time(), "text": result_text}, f, ensure_ascii=False)
                    return result_text
            except:
                live_text2 = get_live_ai_summary()
                return live_text2 if live_text2 else fallback_text
                
        return f"🚨 <b>AI 호출 실패</b> (사유: {error_str})<br><br>{fallback_text}"

def get_news_score(title, stock_name):
    for bad in EXCLUDE_NEWS_KEYWORDS:
        if bad in title: return -1
        
    score = 10 
    aliases = [stock_name]
    if stock_name == "S-Oil": aliases.extend(["에쓰오일", "SOil", "S-OIL"])
    elif "홀딩스" in stock_name: aliases.append(stock_name.replace("홀딩스", ""))

    has_stock = any(alias in title for alias in aliases if len(alias) >= 2)
    has_biz = any(biz in title for biz in BUSINESS_NEWS_KEYWORDS)

    if has_stock: score += 5
    if has_biz: score += 4
    
    return score

def fetch_real_news(keyword, stock_code="", limit=1):
    candidates = []
    
    try:
        search_query = f"{keyword} 주식" if len(keyword) < 4 else keyword
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://search.naver.com/search.naver?where=news&query={encoded_query}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=4)
        soup = BeautifulSoup(res.text, "html.parser")
        
        tit_tags = soup.find_all("a", class_="news_tit")
        for tit_tag in tit_tags:
            raw_title = tit_tag.text.strip()
            link = tit_tag.get("href", "")
            press = "관련뉴스"
            parent = tit_tag.find_parent("div", class_="news_wrap")
            if parent:
                press_tag = parent.find("a", class_="info press")
                if press_tag: 
                    press = press_tag.text.replace("언론사 선정", "").strip()
                    
            score = get_news_score(raw_title, keyword)
            if score > 0: 
                candidates.append({"title": raw_title, "press": press, "link": link, "score": score})
    except: pass

    if len(candidates) < limit and stock_code:
        try:
            code = str(stock_code).zfill(6)
            d_url = f"https://finance.daum.net/api/quotes/A{code}/news?page=1&perPage=10"
            d_headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://finance.daum.net/quotes/A{code}", "Accept": "application/json"}
            d_res = requests.get(d_url, headers=d_headers, timeout=4)
            if d_res.status_code == 200:
                for item in d_res.json().get("data", []):
                    raw_title = re.sub(r'<[^>]+>', '', item.get("title", "")).replace('&quot;', '"').replace('&amp;', '&')
                    link = f"https://finance.daum.net/news/{item.get('newsId')}"
                    press = item.get("cpKorName", "증권뉴스")
                    score = get_news_score(raw_title, keyword)
                    if score > 0: 
                        candidates.append({"title": raw_title, "press": press, "link": link, "score": score})
        except: pass

    if stock_code:
        code = str(stock_code).zfill(6)
        candidates.append({"title": f"[{keyword}] 실시간 주가 분석 및 리포트 바로가기", "press": "다음금융", "link": f"https://finance.daum.net/quotes/A{code}#news/stock", "score": 0.8})
        candidates.append({"title": f"[{keyword}] 실시간 주요 뉴스 및 공시 보러가기", "press": "네이버금융", "link": f"https://finance.naver.com/item/news.naver?code={code}", "score": 0.9})
        candidates.append({"title": f"[{keyword}] 실시간 투자자 종목토론실", "press": "네이버게시판", "link": f"https://finance.naver.com/item/board.naver?code={code}", "score": 0.7})

    candidates.sort(key=lambda x: x["score"], reverse=True)
    unique_news = []
    seen_titles = set()
    for item in candidates:
        clean_title = re.sub(r'\[.*?\]', '', item['title']).strip()
        clean_title = re.sub(r'\W+', '', clean_title)
        if not clean_title: clean_title = item['title']

        if clean_title not in seen_titles:
            seen_titles.add(clean_title)
            unique_news.append(item)
            if len(unique_news) == limit:
                break

    return unique_news

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

def get_us_30y_yield():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/^TYX"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta = res.json()['chart']['result'][0]['meta']
        price = meta['regularMarketPrice']
        prev = meta['previousClose']
        diff = price - prev
        rate = (diff / prev) * 100
        return {
            "name": "미국채 30년물", "code_key": "US30Y",
            "value": f"{price:.3f}%", "change_val": f"{abs(diff):.3f}bp",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except:
        return {"name": "미국채 30년물", "code_key": "US30Y", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_gold_price():
    try:
        url_gold = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
        res_gold = requests.get(url_gold, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta_gold = res_gold.json()['chart']['result'][0]['meta']
        gold_price_usd = meta_gold['regularMarketPrice']
        gold_prev_usd = meta_gold['previousClose']

        url_krw = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X"
        res_krw = requests.get(url_krw, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta_krw = res_krw.json()['chart']['result'][0]['meta']
        krw_rate = meta_krw['regularMarketPrice']
        krw_prev = meta_krw['previousClose']

        price_krw_per_don = (gold_price_usd / 31.1034768) * 3.75 * krw_rate
        prev_krw_per_don = (gold_prev_usd / 31.1034768) * 3.75 * krw_prev

        diff = price_krw_per_don - prev_krw_per_don
        rate = (diff / prev_krw_per_don) * 100

        return {
            "name": "금시세 (1돈)", "code_key": "GOLD_DON",
            "value": f"{price_krw_per_don:,.0f}원", "change_val": f"{diff:+,.0f}원",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except:
        return {"name": "금시세 (1돈)", "code_key": "GOLD_DON", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_silver_price():
    try:
        url_silver = "https://query1.finance.yahoo.com/v8/finance/chart/SI=F"
        res_silver = requests.get(url_silver, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta_silver = res_silver.json()['chart']['result'][0]['meta']
        silver_price_usd = meta_silver['regularMarketPrice']
        silver_prev_usd = meta_silver['previousClose']

        url_krw = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X"
        res_krw = requests.get(url_krw, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta_krw = res_krw.json()['chart']['result'][0]['meta']
        krw_rate = meta_krw['regularMarketPrice']
        krw_prev = meta_krw['previousClose']

        price_krw_per_don = (silver_price_usd / 31.1034768) * 3.75 * krw_rate
        prev_krw_per_don = (silver_prev_usd / 31.1034768) * 3.75 * krw_prev

        diff = price_krw_per_don - prev_krw_per_don
        rate = (diff / prev_krw_per_don) * 100

        return {
            "name": "은시세 (1돈)", "code_key": "SILVER_DON",
            "value": f"{price_krw_per_don:,.0f}원", "change_val": f"{diff:+,.0f}원",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except:
        return {"name": "은시세 (1돈)", "code_key": "SILVER_DON", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_oil_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta = res.json()['chart']['result'][0]['meta']
        price = meta['regularMarketPrice']
        prev = meta['previousClose']
        diff = price - prev
        rate = (diff / prev) * 100
        return {
            "name": "국제유가 (WTI)", "code_key": "OIL",
            "value": f"${price:,.2f}", "change_val": f"{diff:+,.2f}",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except:
        return {"name": "국제유가 (WTI)", "code_key": "OIL", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_jpy_krw_rate():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/JPYKRW=X"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        meta = res.json()['chart']['result'][0]['meta']
        price = meta['regularMarketPrice'] * 100
        prev = meta['previousClose'] * 100
        diff = price - prev
        rate = (diff / prev) * 100
        return {
            "name": "엔·원 환율 (100엔)", "code_key": "JPYKRW",
            "value": f"{price:,.2f}원", "change_val": f"{diff:+.2f}원",
            "change_rate": abs(rate),
            "is_up": diff > 0, "is_down": diff < 0
        }
    except:
        return {"name": "엔·원 환율 (100엔)", "code_key": "JPYKRW", "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_index_data_robust(name, key, mobile_code, pc_code):
    try:
        url = f"https://m.stock.naver.com/api/index/{mobile_code}/basic"
        res = requests.get(url, headers=get_headers(), timeout=3)
        if res.status_code == 200:
            data = res.json()
            cd = str(data.get("compareToPreviousPrice", {}).get("code", "3"))
            return {
                "name": name, "code_key": key, "value": data.get("closePrice", "-"),
                "change_val": data.get("compareToPreviousClosePrice", "0"),
                "change_rate": abs(float(data.get("fluctuationsRatio", 0))),
                "is_up": cd in ["1", "2"], "is_down": cd in ["4", "5"]
            }
    except: pass

    try:
        url = f"https://finance.naver.com/sise/sise_index.naver?code={pc_code}"
        res = requests.get(url, headers=get_headers(), timeout=3)
        soup = BeautifulSoup(res.content.decode("euc-kr", "replace"), "html.parser")

        val_el = soup.find(id="now_value")
        change_el = soup.find(id="change_value_and_rate")

        if val_el and change_el:
            val = val_el.text.strip()
            change_text = change_el.text.strip()

            is_up = "red01" in str(change_el) or "+" in change_text
            is_down = "nv01" in str(change_el) or "-" in change_text

            nums = re.findall(r'[\d\.]+', change_text)
            c_val = nums[0] if len(nums) > 0 else "0"
            c_rate = nums[1] if len(nums) > 1 else "0"

            return {
                "name": name, "code_key": key, "value": val,
                "change_val": c_val,
                "change_rate": abs(float(c_rate)),
                "is_up": is_up, "is_down": is_down
            }
    except: pass

    return {"name": name, "code_key": key, "value": "-", "change_val": "0", "change_rate": 0.0, "is_up": False, "is_down": False}

def get_market_indices():
    results = []
    results.append(get_index_data_robust("코스피 (KOSPI)", "KOSPI", "KOSPI", "KOSPI"))
    results.append(get_index_data_robust("코스닥 (KOSDAQ)", "KOSDAQ", "KOSDAQ", "KOSDAQ"))
    results.append(get_index_data_robust("코스피 200", "KPI200", "KPI200", "KPI200"))

    results.append(get_exchange_rate())         
    results.append(get_jpy_krw_rate())          
    results.append(get_us_10y_yield())          
    results.append(get_us_30y_yield())          
    results.append(get_gold_price())            
    results.append(get_silver_price())          
    results.append(get_oil_price())             

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
            res = requests.get(u, headers=get_headers(), timeout=5)
            if res.status_code == 200:
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
                                code = code_match.group(1) if code_match else ""
                                price = tds[2].text.strip()
                                rate_text = tds[4].text.strip().replace("%", "").replace(",", "")
                                try:
                                    stocks[name] = {"price": price, "rate": float(rate_text), "code": code, "market": market}
                                except: pass
        except: pass

    if len(stocks) < 50:
        daum_headers = get_headers(is_daum=True)
        for market, m_code in [("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")]:
            try:
                url = f"https://finance.daum.net/api/trend/market_capitalization?page=1&perPage=200&market={m_code}"
                res = requests.get(url, headers=daum_headers, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("data", []):
                        name = item.get("name")
                        price = f"{item.get('tradePrice', 0):,}"
                        rate = float(item.get("changeRate", 0)) * 100
                        if item.get("change") in ["FALL", "MINUS"]:
                            rate = -rate
                        code = item.get("symbolCode", "")[1:] 
                        if name:
                            stocks[name] = {"price": price, "rate": round(rate, 2), "code": code, "market": market}
            except: pass

    return stocks

def calculate_sectors(sector_dict, stock_data):
    sector_stats = []
    
    for sec_name, stock_names in sector_dict.items():
        try:
            matched = []
            for sname in stock_names:
                if sname in stock_data:
                    matched.append({"name": sname, **stock_data[sname]})

            if not matched: 
                continue

            matched.sort(key=lambda x: abs(x["rate"]), reverse=True)
            top_3_stocks = matched[:3]
            avg_r = sum(s["rate"] for s in matched) / len(matched)
            
            sector_stats.append({
                "name": sec_name, 
                "rate": round(avg_r, 2), 
                "stocks": top_3_stocks,
                "lead_stock": top_3_stocks[0]["name"]
            })
        except Exception:
            pass

    if not sector_stats:
        return [], []

    sector_stats.sort(key=lambda x: x["rate"], reverse=True)
    top_sectors = sector_stats[:3]
    bot_sectors = sector_stats[-3:][::-1]
    
    for s in top_sectors + bot_sectors:
        news_items = []
        for st in s["stocks"]:
            st_news = fetch_real_news(st["name"], st.get("code", ""), limit=1)
            if st_news:
                news_items.extend(st_news)
        s["news"] = news_items

    return top_sectors, bot_sectors

def send_kakao_alert(indices, k200_top, k150_top):
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
            print(f"[ERROR] 카카오 토큰 갱신 실패: {t_res}")
            return

        kst_now = datetime.now(timezone(timedelta(hours=9)))
        date_str = kst_now.strftime("%m/%d 15:30 마감")

        kospi = next((x for x in indices if "코스피 (KOSPI)" in x["name"]), {})
        kosdaq = next((x for x in indices if "코스닥" in x["name"]), {})
        fx = next((x for x in indices if "환율" in x["name"]), {})

        k_sign = "▲ +" if kospi.get("is_up") else ("▼ -" if kospi.get("is_down") else "")
        kq_sign = "▲ +" if kosdaq.get("is_up") else ("▼ -" if kosdaq.get("is_down") else "")
        fx_sign = "▲ +" if fx.get("is_up") else ("▼ -" if fx.get("is_down") else "")

        k200_lead = k200_top[0]["name"] if k200_top else "집계중"
        k150_lead = k150_top[0]["name"] if k150_top else "집계중"

        msg_text = (
            f"📊 [정규장 마감 리포트] {date_str}\n\n"
            f"• 코스피: {kospi.get('value')} ({k_sign}{abs(kospi.get('change_rate', 0)):.2f}%)\n"
            f"• 코스닥: {kosdaq.get('value')} ({kq_sign}{abs(kosdaq.get('change_rate', 0)):.2f}%)\n"
            f"• 원·달러: {fx.get('value')} ({fx_sign}{abs(fx.get('change_rate', 0)):.2f}%)\n"
            f"• 강세섹터: {k200_lead} / {k150_lead}\n\n"
            f"언제든 접속 시 실시간 시세가 자동 동기화됩니다."
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
                "button_title": "📊 실시간 대시보드 바로가기",
            })
        }
        s_res = requests.post(send_url, headers=headers, data=payload, timeout=5)
        if s_res.status_code == 200:
            print("[SUCCESS] 카카오톡 발송 완료")
        else:
            print(f"[ERROR] 카카오톡 발송 실패: {s_res.text}")
    except Exception as e:
        print(f"[ERROR] 카카오톡 전송 중 오류: {e}")

def render_html(indices, k200_top, k200_bot, k150_top, k150_bot, ai_market_summary):
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

    def build_sector_list(sectors):
        if not sectors: 
            return '<div class="sector-item" style="color:#ef4444; font-weight:700;">섹터 로딩 오류가 발생했습니다.</div>'
        html = ""
        for s in sectors:
            r = s["rate"]
            color_class = "text-up" if r > 0 else ("text-down" if r < 0 else "text-flat")
            stock_tags = "".join([f'<span class="stock-pill"><span class="stock-name">{st["name"]}</span> <b class="stock-rate {"text-up" if st["rate"]>0 else "text-down"}">{st["rate"]:+.2f}%</b> <span class="stock-price">({st["price"]}원)</span></span>' for st in s.get("stocks", [])])

            news_tags = "".join([f'<div class="sector-news">📰 <a href="{n["link"]}" target="_blank" rel="noopener noreferrer" class="news-link">[{n["press"]}] {n["title"]}</a></div>' for n in s.get("news", [])])

            html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{r:+.2f}%</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
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
        .grid-indices {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 24px; }}
        .card {{ background: #fff; padding: 14px 10px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); text-align: center; border: 1px solid #e2e8f0; }}
        .card-title {{ font-size: 0.80rem; font-weight: 600; color: #475569; margin-bottom: 6px; }}
        .card-value {{ font-size: 1.20rem; font-weight: 800; color: #0f172a; margin-bottom: 6px; }}
        .badge {{ display: inline-block; font-size: 0.75rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; }}

        .market-ai-box {{ background: #eff6ff; border-radius: 12px; border: 1px solid #bfdbfe; padding: 18px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
        .market-ai-header {{ font-size: 1.1rem; font-weight: 800; color: #1d4ed8; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }}
        .market-ai-content {{ font-size: 0.98rem; line-height: 1.65; color: #1e293b; font-weight: 500; text-align: justify; word-break: keep-all; }}

        .group-title {{ font-size: 1.15rem; font-weight: 800; margin: 26px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #cbd5e1; }}
        .section-title {{ font-size: 0.95rem; font-weight: 700; margin-bottom: 10px; }}
        .sector-box {{ background: #fff; border-radius: 12px; border: 1px solid #e2e8f0; padding: 16px; margin-bottom: 18px; }}
        .sector-item {{ padding: 14px 0; border-bottom: 1px solid #f1f5f9; }}
        .sector-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
        .sector-name {{ font-weight: 800; font-size: 1.02rem; }}

        .stock-container {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }}
        .stock-pill {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 4px 9px; font-size: 0.82rem; }}

        .sector-news {{ font-size: 0.86rem; line-height: 1.55; color: #1e293b; background: #eff6ff; border-radius: 8px; padding: 8px 12px; margin-bottom: 6px; border-left: 3px solid #3b82f6; font-weight: 500; }}
        .news-link {{ color: #1d4ed8; text-decoration: none; }}
        .news-link:hover {{ text-decoration: underline; }}

        .text-up {{ color: #e11d48 !important; font-weight: 700; }}
        .text-down {{ color: #2563eb !important; font-weight: 700; }}
        .text-flat {{ color: #64748b !important; font-weight: 700; }}
        .bg-up-light {{ background-color: #ffe4e6 !important; }}
        .bg-down-light {{ background-color: #dbeafe !important; }}
        .bg-gray-100 {{ background-color: #f1f5f9 !important; }}
    </style>
</head>
<body>
<!-- 🔐 비밀번호 잠금 화면 시작 -->
<div id="lock-screen" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: #f3f4f6; z-index: 9999; display: flex; flex-direction: column; justify-content: center; align-items: center;">
    <div style="background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center;">
        <h2 style="margin-top: 0; margin-bottom: 20px; color: #111827; font-weight: 800;">🔒 대시보드 잠금</h2>
        <input type="password" id="pw-input" placeholder="비밀번호를 입력하세요" style="width: 100%; box-sizing: border-box; padding: 12px; font-size: 1.1rem; border: 1.5px solid #d1d5db; border-radius: 8px; margin-bottom: 15px; outline: none; text-align: center;">
        <button onclick="checkPassword()" style="width: 100%; padding: 12px; font-size: 1.1rem; background-color: #3b82f6; color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: bold;">입장하기</button>
        <p id="pw-error" style="color: #ef4444; margin-top: 15px; font-weight: 600; display: none;">비밀번호가 틀렸습니다.</p>
    </div>
</div>

<script>
    // 💡 여기에 원하는 비밀번호를 설정하세요! (현재는 4203)
    const SECRET_PASSWORD = "4203";

    function checkPassword() {{
        const input = document.getElementById('pw-input').value;
        if (input === SECRET_PASSWORD) {{
            document.getElementById('lock-screen').style.display = 'none';
            // 💡 탭 이동, 뒤로가기 시에도 비밀번호가 풀리지 않도록 localStorage 유지
            localStorage.setItem('isUnlocked', 'true');
        }} else {{
            document.getElementById('pw-error').style.display = 'block';
        }}
    }}

    window.onload = function() {{
        // 💡 localStorage 확인으로 새 창을 열어도 비밀번호 창 안 뜸
        if (localStorage.getItem('isUnlocked') === 'true') {{
            document.getElementById('lock-screen').style.display = 'none';
        }}
        document.getElementById('pw-input').addEventListener('keypress', function (e) {{
            if (e.key === 'Enter') {{
                checkPassword();
            }}
        }});
    }}
</script>
<!-- 🔐 비밀번호 잠금 화면 끝 -->
    <header><h1>📊 실시간 국내 증시 대시보드</h1></header>
    <div class="grid-indices">{index_cards}</div>

    <div class="market-ai-box">
        <div class="market-ai-header">🤖 주식시장 전체 AI 시황 분석</div>
        <div class="market-ai-content">{ai_market_summary}</div>
    </div>

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
    indices = get_market_indices()
    stock_data = get_market_stocks()

    k200_top, k200_bot = calculate_sectors(KOSPI200_SECTORS, stock_data)
    k150_top, k150_bot = calculate_sectors(KOSDAQ150_SECTORS, stock_data)

    ai_market_summary = generate_ai_market_summary(indices, k200_top, k200_bot, k150_top, k150_bot)

    render_html(indices, k200_top, k200_bot, k150_top, k150_bot, ai_market_summary)

    send_kakao_alert(indices, k200_top, k150_top)
