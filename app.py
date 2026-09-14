import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
import io
import os
import json

# GitHub Secrets에서 카카오 토큰 가져오기 (없으면 에러 방지용 빈 문자열)
KAKAO_TOKEN = os.environ.get("KAKAO_TOKEN", "")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

def fetch_market_data():
    tickers = {
        "필라델피아 반도체": "^SOX", "나스닥 100": "^NDX", "S&P 500": "^GSPC", 
        "VIX 지수": "^VIX", "원/달러 환율": "KRW=X", "미 10년물 금리": "^TNX", 
        "국제 은(Silver)": "SI=F"
    }
    data = {}
    
    # 1. 야후 파이낸스
    for name, ticker in tickers.items():
        try:
            ticker_data = yf.download(ticker, period="1d", progress=False)
            data[name] = round(ticker_data['Close'].iloc[-1].item(), 2) if not ticker_data.empty else "N/A"
        except:
            data[name] = "Error"

    # 2. 은 가격 (원/돈)
    try:
        silver_usd_oz = data.get("국제 은(Silver)", 0)
        krw_usd = data.get("원/달러 환율", 0)
        if isinstance(silver_usd_oz, (int, float)) and isinstance(krw_usd, (int, float)):
            data["은 가격(원/돈)"] = format(int((silver_usd_oz * krw_usd) / 31.1034768 * 3.75), ",")
        else:
            data["은 가격(원/돈)"] = "N/A"
    except:
        data["은 가격(원/돈)"] = "Error"

    # 3. 두바이유
    try:
        url = "https://finance.naver.com/marketindex/materialDetail.naver?marketindexCd=OIL_DU"
        res = requests.get(url, headers=HEADERS)
        dfs = pd.read_html(io.StringIO(res.text))
        data["두바이유"] = dfs[0].iloc[0, 1]
    except:
        data["두바이유"] = "Error"

    # 4. 연준 데이터
    def get_fred_data(series_id):
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        res = requests.get(url, headers=HEADERS)
        df = pd.read_csv(io.StringIO(res.text), parse_dates=['DATE'], index_col='DATE')
        return df[series_id].dropna().iloc[-1]
    
    try:
        data["연준 순유동성(B)"] = round((get_fred_data('WALCL') - get_fred_data('WTREGEN') - get_fred_data('RRPONTSYD')) / 1000, 2)
        data["역레포(ON RRP)(B)"] = round(get_fred_data('RRPONTSYD') / 1000, 2)
        data["지급준비금(B)"] = round(get_fred_data('WRESBAL') / 1000, 2)
    except:
        data["연준 순유동성(B)"] = data["역레포(ON RRP)(B)"] = data["지급준비금(B)"] = "Error"

    # 5. CNN 공포탐욕지수
    try:
        cnn_headers = HEADERS.copy()
        cnn_headers['Accept'] = 'application/json'
        fgi_res = requests.get('https://production.dataviz.cnn.io/index/fearandgreed/graphdata', headers=cnn_headers)
        data["CNN 공포탐욕지수"] = round(fgi_res.json()['fear_and_greed']['score'], 1) if fgi_res.status_code == 200 else "N/A"
    except:
        data["CNN 공포탐욕지수"] = "Error"

    return data

def create_html(data):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_content = f"""
    <!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8"><title>글로벌 금융 대시보드</title>
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; background: #f4f7f6; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
        h1 {{ text-align: center; color: #333; }} .time {{ text-align: right; color: #888; margin-bottom: 20px; }}
        .title {{ font-size: 1.5em; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-top: 30px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 20px; }}
        .card {{ background: #fdfdfd; border: 1px solid #ddd; padding: 20px; border-radius: 8px; text-align: center; }}
        .card h3 {{ margin: 0; font-size: 1.1em; color: #555; }} .card p {{ margin: 10px 0 0 0; font-size: 1.8em; font-weight: bold; color: #2980b9; }}
    </style></head>
    <body><div class="container">
        <h1>🌐 글로벌 금융 마켓 실시간 모니터링</h1><div class="time">업데이트 시간: {current_time}</div>
        
        <div class="title">📈 주요 지수</div><div class="grid">
            <div class="card"><h3>필라델피아 반도체</h3><p>{data.get('필라델피아 반도체')}</p></div>
            <div class="card"><h3>나스닥 100</h3><p>{data.get('나스닥 100')}</p></div>
            <div class="card"><h3>S&P 500</h3><p>{data.get('S&P 500')}</p></div>
            <div class="card"><h3>VIX 지수</h3><p>{data.get('VIX 지수')}</p></div>
        </div>
        <div class="title">💱 환율 & 금리 & 원자재</div><div class="grid">
            <div class="card"><h3>원/달러 환율</h3><p>{data.get('원/달러 환율')}</p></div>
            <div class="card"><h3>미 10년물 금리</h3><p>{data.get('미 10년물 금리')}%</p></div>
            <div class="card"><h3>은 가격 (원/돈)</h3><p>{data.get('은 가격(원/돈)')}</p></div>
            <div class="card"><h3>두바이유</h3><p>${data.get('두바이유')}</p></div>
        </div>
        <div class="title">🏦 연준 유동성 & 투심</div><div class="grid">
            <div class="card"><h3>연준 순유동성</h3><p>${data.get('연준 순유동성(B)')}B</p></div>
            <div class="card"><h3>역레포 (ON RRP)</h3><p>${data.get('역레포(ON RRP)(B)')}B</p></div>
            <div class="card"><h3>지급준비금</h3><p>${data.get('지급준비금(B)')}B</p></div>
            <div class="card"><h3>CNN 공포탐욕지수</h3><p>{data.get('CNN 공포탐욕지수')}</p></div>
        </div>
    </div></body></html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

def send_kakao(data):
    if not KAKAO_TOKEN: return
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {KAKAO_TOKEN}"}
    msg = f"📊 [뉴욕 마감 실시간 브리핑]\n\n📌 반도체: {data.get('필라델피아 반도체')}\n📌 나스닥100: {data.get('나스닥 100')}\n📌 원/달러: {data.get('원/달러 환율')}원\n📌 순유동성: ${data.get('연준 순유동성(B)')}B\n📌 공포탐욕: {data.get('CNN 공포탐욕지수')}"
    
    # 깃허브 사용자명에 맞춰 아래 URL의 rmadh6418-ai 부분을 수정하세요.
    github_pages_url = "https://rmadh6418-ai.github.io/stock-dashboard/"
    
    payload = {
        "template_object": json.dumps({
            "object_type": "text", "text": msg,
            "link": {"web_url": github_pages_url, "mobile_web_url": github_pages_url},
            "button_title": "대시보드 보기"
        })
    }
    requests.post(url, headers=headers, data=payload)

if __name__ == "__main__":
    market_data = fetch_market_data()
    create_html(market_data)
    send_kakao(market_data)
