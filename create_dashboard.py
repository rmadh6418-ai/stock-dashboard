import yfinance as yf
import pandas as pd
import requests
from datetime import datetime

# 데이터 수집 함수
def fetch_market_data():
    tickers = {
        "필라델피아 반도체": "^SOX", "나스닥 생명공학": "^NBI", "S&P 500": "^GSPC", 
        "나스닥 100": "^NDX", "다우존스": "^DJI", "달러인덱스(DXY)": "DX-Y.NYB", 
        "원/달러 환율": "KRW=X", "엔/달러 환율": "JPY=X", "미 10년물 금리": "^TNX", 
        "미 30년물 금리": "^TYX", "VIX 지수": "^VIX", "WTI 원유": "CL=F", 
        "브렌트유": "BZ=F", "국제 은(Silver)": "SI=F"
    }
    
    data = {}
    
    # 1. 야후 파이낸스 데이터 가져오기
    print("야후 파이낸스 데이터 수집 중...")
    for name, ticker in tickers.items():
        try:
            ticker_data = yf.download(ticker, period="1d", progress=False)
            if not ticker_data.empty:
                data[name] = round(ticker_data['Close'].iloc[-1].item(), 2)
            else:
                data[name] = "N/A"
        except:
            data[name] = "Error"

    # 2. 국내 은 가격 계산 (1돈 = 3.75g 적용)
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

    # 3. 두바이유 웹 크롤링 (네이버 금융)
    print("두바이유 데이터 수집 중...")
    try:
        url = "https://finance.naver.com/marketindex/materialDetail.naver?marketindexCd=OIL_DU"
        res = requests.get(url)
        dfs = pd.read_html(res.text)
        data["두바이유"] = dfs[0].iloc[0, 1]
    except:
        data["두바이유"] = "Error"
        
    data["코스피200 선물"] = "API 연동 필요"

    # 4. 연준 유동성 지표 (FRED 직접 크롤링)
    print("연준 데이터 수집 중...")
    def get_fred_data(series_id):
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        df = pd.read_csv(url, parse_dates=['DATE'], index_col='DATE')
        return df[series_id].dropna().iloc[-1]

    try:
        assets = get_fred_data('WALCL')
        tga = get_fred_data('WTREGEN')
        on_rrp = get_fred_data('RRPONTSYD')
        reserves = get_fred_data('WRESBAL')
        
        data["연준 순유동성(B)"] = round((assets - tga - on_rrp) / 1000, 2)
        data["역레포(ON RRP)(B)"] = round(on_rrp / 1000, 2)
        data["지급준비금(B)"] = round(reserves / 1000, 2)
    except:
        data["연준 순유동성(B)"] = data["역레포(ON RRP)(B)"] = data["지급준비금(B)"] = "Error"

    # 5. CNN 공포탐욕지수
    print("투심 지표 수집 중...")
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

# HTML 파일 생성 함수
def create_html_dashboard(data):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>글로벌 금융 마켓 실시간 모니터링</title>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; background-color: #f4f7f6; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
            h1 {{ text-align: center; color: #333; }}
            .time {{ text-align: right; color: #888; font-size: 0.9em; margin-bottom: 20px; }}
            .section-title {{ font-size: 1.5em; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; margin-top: 30px; }}
            .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-top: 20px; }}
            .card {{ background: #fdfdfd; border: 1px solid #ddd; padding: 20px; border-radius: 8px; text-align: center; }}
            .card h3 {{ margin: 0; font-size: 1.1em; color: #555; }}
            .card p {{ margin: 10px 0 0 0; font-size: 1.8em; font-weight: bold; color: #2980b9; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌐 글로벌 금융 마켓 실시간 모니터링</h1>
            <div class="time">업데이트 시간: {current_time}</div>
            
            <div class="section-title">📈 주요 지수</div>
            <div class="grid">
                <div class="card"><h3>필라델피아 반도체</h3><p>{data.get('필라델피아 반도체')}</p></div>
                <div class="card"><h3>나스닥 100</h3><p>{data.get('나스닥 100')}</p></div>
                <div class="card"><h3>S&P 500</h3><p>{data.get('S&P 500')}</p></div>
                <div class="card"><h3>VIX 지수</h3><p>{data.get('VIX 지수')}</p></div>
            </div>

            <div class="section-title">💱 환율 & 금리 & 원자재</div>
            <div class="grid">
                <div class="card"><h3>원/달러 환율</h3><p>{data.get('원/달러 환율')}</p></div>
                <div class="card"><h3>미 10년물 국채금리</h3><p>{data.get('미 10년물 금리')}%</p></div>
                <div class="card"><h3>은 가격 (원/돈)</h3><p>{data.get('은 가격(원/돈)')}</p></div>
                <div class="card"><h3>두바이유</h3><p>${data.get('두바이유')}</p></div>
            </div>

            <div class="section-title">🏦 연준 유동성 & 투심</div>
            <div class="grid">
                <div class="card"><h3>연준 순유동성</h3><p>${data.get('연준 순유동성(B)')}B</p></div>
                <div class="card"><h3>역레포 (ON RRP)</h3><p>${data.get('역레포(ON RRP)(B)')}B</p></div>
                <div class="card"><h3>지급준비금</h3><p>${data.get('지급준비금(B)')}B</p></div>
                <div class="card"><h3>CNN 공포탐욕지수</h3><p>{data.get('CNN 공포탐욕지수')}</p></div>
            </div>
        </div>
    </body>
    </html>
    """
    
    with open("market_dashboard.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("✅ 'market_dashboard.html' 파일이 성공적으로 생성되었습니다!")

if __name__ == "__main__":
    market_data = fetch_market_data()
    create_html_dashboard(market_data)
