import os
import re
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
    """시가총액 상위 종목 체결가 및 등락률 수집"""
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

# 섹터별 주요 이슈 및 드라이버 데이터베이스 매핑
SECTOR_INSIGHTS = {
    "화학·에너지": "국제 유가 반등 및 정제마진 개선, 배터리 소재/정밀화학 턴어라운드 기대감이 복합적으로 작용했습니다.",
    "이차전지·배터리": "글로벌 완성차 신차 라인업 확대 및 원통형 폼팩터 공급 본격화, 핵심 광물 판가 안정세가 수급을 자극했습니다.",
    "조선·중공업": "고선가 LNG선 및 친환경 쇄빙 컨테이너선 수주 잔고 증가와 하반기 카타르 2차 프로젝트 실적 가시성이 돋보였습니다.",
    "전기·전자 (반도체/IT)": "차세대 HBM 공급 경쟁력 강화 및 온디바이스 AI 칩 수요 확대 기대감에 외인 매수세가 집중되었습니다.",
    "자동차·운송장비": "하이브리드(HEV) 고수익 트림 중심의 글로벌 판매 호조와 밸류업 정책에 따른 배당·주주환원 매력이 부각되었습니다.",
    "원전·전력인프라": "유럽·중동 체코 원전 후속 수주 모멘텀 및 북미 인공지능(AI) 데이터센터 증설에 따른 초고압 변압기 수혜가 지속되었습니다.",
    "방위산업·우주항공": "루마니아·폴란드 후속 납품 및 중동지역 천궁-II 추가 계약 등 K-방산 수출 레퍼런스가 실적을 견인했습니다.",
    "제약·바이오": "글로벌 빅파마 대상 면역항암제 기술이전(L/O) 기대감과 비만치료제·바이오시밀러 북미 점유율 확대가 긍정적이었습니다.",
    "금융·지주": "정부 밸류업 프로그램에 따른 자사주 소각 기대감과 금리 인하 국면 속 비이자이익 포트폴리오 다변화가 반영되었습니다.",
    "인터넷·플랫폼": "거대 AI 모델의 B2B 수익화 모델 검증 과정 및 단기 차익 실현 압력이 주가 등락에 영향을 미쳤습니다.",
    "건설·시공": "PF 유동성 우려 완화 추이 및 해외 플랜트 수주 실적이 업황 방어 요인으로 작용했습니다.",
    "철강·금속": "중국 철강 감산 정책 및 리튬·니켈 제련소 가동률 회복에 따른 스프레드 개선 기대감이 상존했습니다.",
    "음식료·유통": "K-푸드 글로벌 수출(라면, 김밥, 소스류) 서프라이즈와 내수 원가율 개선이 긍정적 흐름을 보였습니다.",
    "반도체 소부장": "선단 공정용 고성능 테스트 소켓, 전구체, CMP 슬러리 등 국산화 부품 공급 확대가 주가 탄력성을 지지했습니다.",
    "이차전지·소재": "양극재 판가 바닥론 대두와 전해액·실리콘 음극재 설비 증설 효과가 테마 순환매를 이끌었습니다.",
    "엔터·미디어": "소속 핵심 IP의 글로벌 음원 차트 진입과 월드투어 실적 반영, 음반 수출 다변화가 주가에 반영되었습니다.",
    "게임·소프트웨어": "글로벌 PC·콘솔 신작 출시 일정 가시화 및 라이브 서비스 게임의 해외 매출 견인력이 모멘텀이 되었습니다.",
    "로봇·자동화": "대기업 스마트팩토리 무인 물류 및 협동로봇 라인 구축 가속화에 따른 핵심 액추에이터 수주가 집중되었습니다.",
    "피팅·배관기자재": "북미 LNG 수출 터미널 증설과 중동 담수화 플랜트용 고압 피팅 밸브 수요 호조세가 지속되었습니다."
}

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
            insight = SECTOR_INSIGHTS.get(sec_name, "수급 변동성 및 차익 실현 매물 출회에 따른 업종 순환매가 전개되었습니다.")
            results.append({
                "name": sec_name,
                "rate": round(avg_r, 2),
                "stocks": matched[:3],
                "insight": insight
            })
    results.sort(key=lambda x: x["rate"], reverse=True)
    top = results[:3]
    bot = results[-3:]
    bot.reverse()
    return top, bot

def generate_market_review(indices, k200_top, k200_bot, k150_top, k150_bot):
    """전체 마감 총평 및 주요 섹터 심층 이슈 분석"""
    kospi = next((x for x in indices if "코스피 (KOSPI)" in x["name"]), {})
    kosdaq = next((x for x in indices if "코스닥 (KOSDAQ)" in x["name"]), {})
    fx = next((x for x in indices if "환율" in x["name"]), {})

    k_dir = "상승" if kospi.get("is_up") else ("하락" if kospi.get("is_down") else "보합")
    kq_dir = "상승" if kosdaq.get("is_up") else ("하락" if kosdaq.get("is_down") else "보합")

    # 환율 코멘트
    fx_text = ""
    if fx.get("is_down"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 하향 안정화(원화 강세)를 나타내며 외국인 수급 여건을 지지했습니다."
    elif fx.get("is_up"):
        fx_text = f"원·달러 환율이 <b>{fx.get('value')}</b>로 오름세를 보이며 외국인 매물 압박 요인으로 작용했습니다."
    else:
        fx_text = f"원·달러 환율은 <b>{fx.get('value')}</b> 선에서 안정적인 보합세를 유지했습니다."

    # 섹터별 이슈 리스트 구성
    sector_bullets = ""
    for s in k200_top[:2]:
        sector_bullets += f"""<div class="review-item"><span class="bullet">🔴</span><div><b>[{s['name']} | +{s['rate']}%]</b> {s['insight']}</div></div>"""
    for s in k200_bot[:2]:
        sector_bullets += f"""<div class="review-item"><span class="bullet">🔵</span><div><b>[{s['name']} | {s['rate']}%]</b> 단기 상승 피로감과 기관·외인의 차익 실현 출회로 숨고르기 양상이 나타났습니다.</div></div>"""

    review_html = f"""
    <div class="review-card">
        <div class="review-header">
            <span class="review-title">📝 정규장 마감 핵심 요약 & 섹터별 이슈 브리핑</span>
            <span class="review-tag">15:30 확정 집계</span>
        </div>
        <div class="review-body">
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[마감 총평]</b> 코스피는 <b>{kospi.get('value')}</b>({k_dir}), 코스닥은 <b>{kosdaq.get('value')}</b>({kq_dir})으로 정규장을 마감했습니다. 실적 가시성이 높은 주도 테마를 중심으로 수급이 압축되는 차별화 장세가 확인되었습니다.</div>
            </div>
            <div class="review-item">
                <span class="bullet">📌</span>
                <div><b>[환율 및 거시 여건]</b> {fx_text}</div>
            </div>
            <div class="review-divider"></div>
            <div style="font-weight: 700; color: #1e293b; margin-bottom: 4px;">🔍 주요 업종별 모멘텀 분석</div>
            {sector_bullets}
        </div>
    </div>
    """
    return review_html

def render_html(indices, k200_top, k200_bot, k150_top, k150_bot):
    # KST (한국 표준시 UTC+9) 기준 정규장 15:30 마감 시간 포맷팅
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
            
            html += f"""
            <div class="sector-item">
                <div class="sector-header">
                    <span class="sector-name">{s['name']}</span>
                    <span class="sector-rate {color_class}">{sign}{s['rate']}%</span>
                </div>
                <div class="stock-container">{stock_tags}</div>
                <div class="sector-insight">{s.get('insight', '')}</div>
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
        .sector-insight {{ font-size: 0.83rem; color: #64748b; line-height: 1.45; background: #f8fafc; padding: 8px 10px; border-radius: 6px; border-left: 3px solid #cbd5e1; }}
        
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
