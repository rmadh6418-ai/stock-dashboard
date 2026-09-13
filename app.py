import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import json
import sys
from datetime import datetime
from fredapi import Fred

# API 키 설정 (GitHub Secrets 또는 Streamlit Secrets에 등록 필요)
FRED_API_KEY = st.secrets.get("FRED_API_KEY", "YOUR_FRED_API_KEY")
KAKAO_TOKEN = st.secrets.get("KAKAO_TOKEN", "YOUR_KAKAO_TOKEN")

def fetch_market_data():
    fred = Fred(api_key=FRED_API_KEY)
    
    # 1. 야후 파이낸스 티커 맵핑
    tickers = {
        "필라델피아 반도체": "^SOX", 
        "나스닥 생명공학": "^NBI", 
        "S&P 500": "^GSPC", 
        "나스닥 100": "^NDX", 
        "다우존스": "^DJI",
        "달러인덱스(DXY)": "DX-Y.NYB", 
        "원/달러 환율": "KRW=X", 
        "엔/달러 환율": "JPY=X",
        "미 10년물 금리": "^TNX", 
        "미 30년물 금리": "^TYX", 
        "VIX 지수": "^VIX",
        "WTI 원유": "CL=F", 
        "브렌트유": "BZ=F",
        "국제 은(Silver)": "SI=F" # 은 가격 연산용
    }
    
    data = {}
    for name, ticker in tickers.items():
        try:
            ticker_data = yf.download(ticker, period="1d", progress=False)
            if not ticker_data.empty:
                data[name] = round(ticker_data['Close'].iloc[-1].item(), 2)
            else:
                data[name] = "N/A"
        except:
            data[name] = "Error"

    # 2. 국내 은 가격 (돈당 변환: 1 트로이온스 = 31.1034768g, 1돈 = 3.75g)
    try:
        silver_usd_oz = data.get("국제 은(Silver)", 0)
        krw_usd = data.get("원/달러 환율", 0)
        if isinstance(silver_usd_oz, (int, float)) and isinstance(krw_usd, (int, float)):
            silver_krw_gram = (silver_usd_oz * krw_usd) / 31.1034768
            data["은 가격(원/돈)"] = format(int(silver_krw_gram * 3.75), ",")
        else:
            data["은 가격(원/돈)"] = "N/A"
    except:
        data["은 가격(원/돈)"] = "Error"

    # 3. 코스피 200 야간선물 (네이버 금융 크롤링 대체용 구조)
    data["코스피200 선물"] = "345.50 (API 연동 필요)" 

    # 4. 연준(Fed) 유동성 지표 (FRED API)
    try:
        assets = fred.get_series('WALCL').iloc[-1]
        tga = fred.get_series('WTREGEN').iloc[-1]
        on_rrp = fred.get_series('RRPONTSYD').iloc[-1]
        reserves = fred.get_series('WRESBAL').iloc[-1]
        
        data["연준 순유동성(B)"] = round((assets - tga - on_rrp) / 1000, 2)
        data["역레포(ON RRP)(B)"] = round(on_rrp / 1000, 2)
        data["지급준비금(B)"] = round(reserves / 1000, 2)
    except:
        data["연준 순유동성(B)"] = data["역레포(ON RRP)(B)"] = data["지급준비금(B)"] = "API Error"

    # 5. CNN 공포탐욕지수
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        fgi_response = requests.get('https://production.dataviz.cnn.io/index/fearandgreed/graphdata', headers=headers)
        if fgi_response.status_code == 200:
            fgi_data = fgi_response.json()
            data["CNN 공포탐욕지수"] = round(fgi_data['fear_and_greed']['score'], 1)
        else:
            data["CNN 공포탐욕지수"] = "N/A"
    except:
        data["CNN 공포탐욕지수"] = "Error"

    return data

def send_kakao_message():
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {KAKAO_TOKEN}"}
    
    market_data = fetch_market_data()
    
    msg = f"📊 [뉴욕 마감 실시간 브리핑]\n\n"
    msg += f"📌 주요 지수\n- SOX: {market_data.get('필라델피아 반도체')}\n- 나스닥100: {market_data.get('나스닥 100')}\n- S&P500: {market_data.get('S&P 500')}\n- 코스피200 선물: {market_data.get('코스피200 선물')}\n\n"
    msg += f"📌 환율 및 금리\n- 원/달러: {market_data.get('원/달러 환율')}원\n- 은 가격(돈당): {market_data.get('은 가격(원/돈)')}원\n- 미 10년물: {market_data.get('미 10년물 금리')}%\n\n"
    msg += f"📌 유동성 & 투심\n- 연준 순유동성: ${market_data.get('연준 순유동성(B)')}B\n- 역레포: ${market_data.get('역레포(ON RRP)(B)')}B\n- 공포탐욕: {market_data.get('CNN 공포탐욕지수')}"
    
    payload = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": msg,
            "link": {"web_url": "https://github.com", "mobile_web_url": "https://github.com"},
            "button_title": "대시보드 확인"
        })
    }
    requests.post(url, headers=headers, data=payload)

# GitHub Actions에서 'cron' 인자로 실행될 때 카카오톡 발송 로직만 처리
if len(sys.argv) > 1 and sys.argv[1] == "cron":
    send_kakao_message()
    sys.exit(0)

# Streamlit 대시보드 UI 랜더링
st.set_page_config(page_title="글로벌 금융 대시보드", layout="wide")
st.title("🌐 글로벌 금융 마켓 실시간 모니터링")

with st.spinner("데이터를 불러오는 중입니다..."):
    data = fetch_market_data()

st.subheader("📈 주요 지수 & 선물")
c1, c2, c3, c4 = st.columns(4)
c1.metric("필라델피아 반도체", data.get("필라델피아 반도체"))
c2.metric("나스닥 100", data.get("나스닥 100"))
c3.metric("S&P 500", data.get("S&P 500"))
c4.metric("코스피200 선물", data.get("코스피200 선물"))

st.subheader("💱 환율 & 금리 & 원자재")
c5, c6, c7, c8 = st.columns(4)
c5.metric("원/달러 환율", data.get("원/달러 환율"))
c6.metric("미 10년물 국채금리", f"{data.get('미 10년물 금리')}%")
c7.metric("WTI 원유", f"${data.get('WTI 원유')}")
c8.metric("은 가격 (원/돈)", data.get("은 가격(원/돈)"))

st.subheader("🏦 연준 유동성 & 투심")
c9, c10, c11, c12 = st.columns(4)
c9.metric("연준 순유동성", f"${data.get('연준 순유동성(B)')}B")
c10.metric("역레포 (ON RRP)", f"${data.get('역레포(ON RRP)(B)')}B")
c11.metric("VIX 지수", data.get("VIX 지수"))
c12.metric("CNN 공포탐욕지수", data.get("CNN 공포탐욕지수"))

if st.button("수동으로 카카오톡 브리핑 보내기"):
    send_kakao_message()
    st.success("카카오톡 메시지가 발송되었습니다!")
