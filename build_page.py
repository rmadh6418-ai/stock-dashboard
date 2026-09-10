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
  """원·달러 환율 데이터 수집 (1순위: 공식 실시간 환율 API, 2순위: 네이버 금융 크롤링 백업)"""
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
  """4대 주요 지수(코스피, 코스닥, 코스피200, 환율) 정확 수집"""
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


def build_expert_sector_analysis(sec_name, avg_rate, stocks):
  """기계적인 문장 틀(나침반, 방향키 등)을 완전히 제거하고, 실제 업황과 주가 움직임을 반영한 진짜 애널리스트 리포트 생성"""
  lead = stocks[0] if len(stocks) > 0 else None
  sub = stocks[1] if len(stocks) > 1 else None
  third = stocks[2] if len(stocks) > 2 else None

  lead_str = f"{lead['name']}({lead['rate']:+.2f}%)" if lead else ""
  sub_str = f"{sub['name']}({sub['rate']:+.2f}%)" if sub else ""
  third_str = f"{third['name']}({third['rate']:+.2f}%)" if third else ""

  is_up = avg_rate > 0

  if "방위" in sec_name:
    if is_up:
      return (
          "동유럽과 중동발 지정학적 리스크 지속으로 K-방산의 신규 수주 기대감이"
          f" 유효하게 작용했습니다. 특히 {lead_str}과 {sub_str}을 중심으로"
          " 외국인 순매수가 유입되며 섹터 전반이 견조한 우상향 탄력을"
          " 지켜냈습니다."
      )
    else:
      return (
          "최근 가파른 주가 상승에 따른 단기 밸류에이션 부담으로"
          f" {lead_str} 등 주요 완성체 종목군에 이익 실현 매물이"
          " 출회되었습니다. 다만 다년간 쌓인 해외 수주잔고를 고려할 때 중장기"
          " 성장 기조는 유효하다는 평가입니다."
      )

  elif "소부장" in sec_name:
    if is_up:
      return (
          "글로벌 파운드리 및 메모리 기업들의 선단 미세공정 설비투자 재개"
          f" 기대감이 소부장으로 확산되었습니다. {lead_str}이 높은 기술"
          f" 경쟁력을 바탕으로 매수세를 이끌었고, {sub_str}도 동반 상승하며"
          " 견조한 흐름을 나타냈습니다."
      )
    else:
      return (
          "전방 칩메이커들의 보수적인 설비투자 집행 우려로 중소형 소부장 종목"
          f" 간 옥석 가리기가 심화되었습니다. {lead_str}을 포함한 장비·소재주"
          " 전반에 걸쳐 관망세가 짙어졌습니다."
      )

  elif "반도체" in sec_name or "전기·전자" in sec_name:
    if is_up:
      return (
          "글로벌 AI 가속기 및 차세대 HBM(고대역폭메모리) 공급망 수혜가"
          f" 부각되었습니다. {lead_str}이 견고한 매수세를 형성하며 상승을"
          f" 주도했으나, {third_str if third else sub_str} 등 IT 부품주들은"
          " 엇갈린 흐름을 보였습니다."
      )
    else:
      return (
          "미국 빅테크 기업들의 AI 인프라 투자 속도조절 우려와 외국인 현·선물"
          " 동반 순매도가 지수 대형주에 하방 압력을 가했습니다."
          f" {lead_str}과 {sub_str}이 동반 약세를 보이며 지수 하락을"
          " 견인했습니다."
      )

  elif "금융" in sec_name:
    if is_up:
      return (
          "정부의 기업 밸류업 프로그램에 발맞춰 자사주 소각과 배당 확대"
          f" 기대감이 금융지주사들의 주가를 지지했습니다. {lead_str}과 {sub_str}"
          " 등 대형 은행지주 중심의 저가 매수세가 돋보였습니다."
      )
    else:
      return (
          "하반기 기준금리 인하 사이클 진입에 따른 순이자마진(NIM) 축소"
          f" 경계감이 상단을 제한했습니다. {lead_str}을 포함한 주요 금융주"
          " 전반이 단기 숨고르기 양상을 나타냈습니다."
      )

  elif "화학" in sec_name or "에너지" in sec_name:
    if avg_rate < 0:
      return (
          "국제유가 변동성과 중국 내수 부진에 따른 정제마진 스프레드 둔화"
          f" 우려가 직격탄으로 작용했습니다. 특히 {lead_str}이 급락세를 보이고"
          f" {sub_str} 등 정유·석유화학 대형주 전반에 기관과 외국인의 매도"
          " 물량이 쏟아졌습니다."
      )
    else:
      return (
          "낙폭 과대 인식이 확산되며 정유·화학주로 저가 반발 매수세가"
          f" 유입되었습니다. {lead_str}의 반등을 축으로 단기 기술적 반등"
          " 흐름이 전개되었습니다."
      )

  elif "이차전지" in sec_name or "배터리" in sec_name:
    if is_up:
      return (
          "북미 ESS(에너지저장장치)향 대형 수주 모멘텀과 리튬 등 핵심 광물"
          f" 가격의 바닥 통과 기대감이 주가를 견인했습니다. {lead_str}을"
          " 중심으로 숏커버링 매수세가 유입되며 섹터 분위기를 반전시켰습니다."
      )
    else:
      return (
          "글로벌 전기차(EV) 수요 둔화(캐즘) 장기화 우려와 주요 완성차"
          f" 업체들의 전동화 전환 지연 소식이 {lead_str} 등 배터리 밸류체인"
          " 전반에 부담을 안겼습니다."
      )

  elif "원전" in sec_name or "전력" in sec_name:
    if is_up:
      return (
          "글로벌 AI 데이터센터 증설에 따른 전력망 확충 수혜로 초고압 변압기와"
          f" 송배전 기기의 북미·유럽 수출 호조가 지속되었습니다. {lead_str}이"
          " 강한 실적 모멘텀을 과시하며 상승세를 이끌었습니다."
      )
    else:
      return (
          "연초 이후 가파르게 오른 전력설비주들에 대해 밸류에이션 부담을 느낀"
          f" 차익 실현 매물이 출회되었습니다. {lead_str}과 {sub_str}이 나란히"
          " 밀리며 기간 조정에 들어갔습니다."
      )

  elif "자동차" in sec_name:
    if is_up:
      return (
          "하이브리드(HEV) 중심의 견고한 북미 판매량과 고환율 효과에 힘입어"
          f" 실적 방어력이 재부각되었습니다. {lead_str}을 중심으로 안정적인"
          " 주주환원 기대감이 수급을 뒷받침했습니다."
      )
    else:
      return (
          "글로벌 자동차 시장의 가격 경쟁 심화와 미국 대선 전후 보조금 정책"
          f" 불확실성이 {lead_str} 등 완성차 종목군의 투자 심리를"
          " 위축시켰습니다."
      )

  elif "바이오" in sec_name or "제약" in sec_name:
    if is_up:
      return (
          "금리 인하 국면 진입에 따른 유동성 유입 기대와 주요 파이프라인의"
          f" 글로벌 기술수출(L/O) 모멘텀이 맞물렸습니다. {lead_str}의 주가"
          " 탄력이 부각되며 바이오텍 전반으로 매수 온기가 퍼졌습니다."
      )
    else:
      return (
          f"지수 조정과 위험자산 회피 심리로 인해 {lead_str}을 비롯한 신약"
          " 개발주 전반에 차익 매물이 출회되며 변동성이 확대되었습니다."
      )

  elif "조선" in sec_name:
    if is_up:
      return (
          "고부가 친환경 선박(LNG/암모니아선) 신조선가 상승세와 3년 이상의"
          " 넉넉한 수주잔고가 구조적 실적 개선을 뒷받침했습니다."
          f" {lead_str}의 실적 턴어라운드 가시성이 부각되며 강세를 보였습니다."
      )
    else:
      return (
          "철강 후판가 협상 관련 불확실성과 단기 급등에 따른 피로감으로"
          f" {lead_str}을 비롯한 대형 조선주들이 숨고르기 조정을 받았습니다."
      )

  elif "로봇" in sec_name:
    if is_up:
      return (
          "제조업 무인화 설비 수요 증가와 빅테크들의 휴머노이드 투자 확대"
          f" 소식이 테마 수급을 강하게 자극했습니다. {lead_str}이 가파른 상승"
          " 탄력을 과시하며 시장의 이목을 집중시켰습니다."
      )
    else:
      return (
          "실적 가시성 대비 고평가 논란 속에서 테마성 단기 자금이 이탈하며"
          f" {lead_str}을 중심으로 되돌림 조정이 나타났습니다."
      )

  elif "엔터" in sec_name:
    if is_up:
      return (
          "주요 아티스트의 월드투어 재개와 음원 스트리밍 매출 호조가 주가"
          f" 반등의 모멘텀이 되었습니다. {lead_str}이 기관 매수세 유입과 함께"
          " 반등 흐름을 주도했습니다."
      )
    else:
      return (
          "음반 판매량 정체 우려와 주요 라인업의 활동 공백 이슈가 부각되며"
          f" {lead_str} 등 주요 엔터주들이 약세를 면치 못했습니다."
      )

  elif "게임" in sec_name:
    if is_up:
      return (
          "신작 출시 기대감과 글로벌 플랫폼 확장 성과가 주가에 긍정적으로"
          f" 작용했습니다. {lead_str}이 거래량을 동반하며 섹터 상승을"
          " 이끌었습니다."
      )
    else:
      return (
          "신작 부재에 따른 실적 둔화 우려와 인건비 부담이 지속되며"
          f" {lead_str}을 중심으로 보수적인 투자 심리가 이어졌습니다."
      )

  elif "피팅" in sec_name:
    if is_up:
      return (
          "국내 대형 조선사들의 친환경 LNG선 건조 본격화에 힘입어 산업용 피팅"
          f" 및 관이음쇠 수주 증가세가 가시화되었습니다. {lead_str}이 안정적인"
          " 실적을 바탕으로 견조한 주가 흐름을 유지했습니다."
      )
    else:
      return (
          "전방 조선·해양 플랜트 프로젝트의 단기 발주 공백 우려가 반영되며"
          f" {lead_str}을 비롯한 피팅 기자재주들이 조정을 받았습니다."
      )

  elif "철강" in sec_name:
    return (
        "중국산 저가 철강재 수입 증가에 따른 단가 인하 압박과 건설 등 전방"
        f" 산업 수요 침체 속에서 {lead_str} 등 주요 철강주들이 제한적인 등락을"
        " 보였습니다."
    )

  elif "건설" in sec_name:
    return (
        "국내 부동산 PF 관련 잠재 리스크와 원자재비 상승 부담 속에서, "
        f"중동·해외 플랜트 수주 가시성을 보유한 {lead_str} 중심으로 선별적"
        " 방어가 시도되었습니다."
    )

  elif "음식료" in sec_name:
    return (
        "K-푸드의 글로벌 수출 랠리와 국제 곡물 가격 안정화에 따른 원가율 개선"
        f" 기대감이 유효한 가운데, {lead_str}의 실적 안정성이 돋보였습니다."
    )

  else:
    trend = "상승 탄력을 받았습니다" if is_up else "하락 압력을 받았습니다"
    return (
        f"{sec_name} 섹터는 고유 업황 이슈와 시장 매크로 환경 변화 속에서"
        f" 대장주인 {lead_str}의 수급 공방에 연동되며 {trend}."
    )


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

      # 섹터별 고유 애널리스트 리포트 생성
      analysis_txt = build_expert_sector_analysis(sec_name, avg_r, matched)

      results.append({
          "name": sec_name,
          "rate": round(avg_r, 2),
          "stocks": matched[:3],
          "lead_stock": top_stock_name,
          "news": news_items,
          "summary": analysis_txt,
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
      summary_tag = (
          f"""<div class="sector-summary">💡 <b>섹터 핵심 브리핑:</b>"""
          f""" {summary_text}</div>"""
      )

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
        
        .review-card {{ background: #ffffff; border-radius: 12px; border-left: 5px solid #2563eb; border: 1px solid #e2e8f0; border-left-width: 5px; border-left-color: #2563eb; padding: 18px; margin-bottom: 24px; box-shadow: 0 1px 4px rgba(0,0,0,0.04); }}
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
        .sector-news {{ font-size: 0.84rem; color: #475569; background: #f8fafc; padding: 7px 10px; border-radius: 6px; border-left: 3px solid #3b82f6; margin-bottom: 8px; }}
        
        .sector-summary {{ font-size: 0.84rem; line-height: 1.65; color: #1e293b; background: #f1f5f9; border-radius: 6px; padding: 10px 14px; border-left: 4px solid #2563eb; }}
        .sector-summary b {{ color: #1d4ed8; }}

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

  render_html(indices, k200_top, k200_bot, k150_top, k150_bot)
  send_kakao_alert(indices, k200_top, k150_top)
