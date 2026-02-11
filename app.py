import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面設定 (強制關閉不必要的選單)
st.set_page_config(page_title="iPad 極速版", layout="wide")

# 2. 側邊欄：將最常動到的放在上面
st.sidebar.header("🚀 極速看盤")
market = st.sidebar.radio("市場", ["台股", "美股"], horizontal=True)
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股" else "TSLA").upper()

# 調整：這裡決定抓取量，是效能關鍵
range_map = {
    "一個月": "1mo", "三個月": "3mo", "六個月": "6mo", 
    "一年": "1y", "三年": "3y", "五年": "5y"
}
selected_range = st.sidebar.selectbox("回推範圍", list(range_map.keys()), index=1) # 預設三個月

cycle_map = {"日線": "1d", "週線": "1wk", "月線": "1mo"}
selected_cycle = st.sidebar.selectbox("週期", list(cycle_map.keys()), index=0)

# 3. 極速資料抓取
@st.cache_data(ttl=600, show_spinner="載入中...")
def quick_fetch(symbol, market, period, interval):
    s = f"{symbol}.TW" if market == "台股" else symbol
    try:
        df = yf.download(s, period=period, interval=interval, progress=False)
        if df.empty and market == "台股":
            df = yf.download(f"{symbol}.TWO", period=period, interval=interval, progress=False)
        # 修正 yfinance 新版 multi-index 問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return pd.DataFrame()

# 4. 神奇九轉 (限制僅計算目前的畫面，不全算)
def calculate_td_fast(df):
    if len(df) < 5: return [0]*len(df), [0]*len(df)
    close = df['Close'].values
    buy_s, sell_s = [0]*len(df), [0]*len(df)
    cb, cs = 0, 0
    for i in range(4, len(df)):
        if close[i] < close[i-4]: cb += 1; buy_s[i] = cb
        else: cb = 0
        if close[i] > close[i-4]: cs += 1; sell_s[i] = cs
        else: cs = 0
    return buy_s, sell_s

# --- 執行流程 ---
df = quick_fetch(symbol, market, range_map[selected_range], cycle_map[selected_cycle])

if not df.empty:
    # 僅計算必要指標
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    
    # 布林
    std = df['Close'].rolling(20).std()
    df['UB'] = df['MA20'] + (std * 2)
    df['LB'] = df['MA20'] - (std * 2)

    # 繪圖
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])

    # K線
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="K線", increasing_line_color='red', decreasing_line_color='green'
    ), row=1, col=1)

    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], name="MA5", line=dict(width=1, color='blue')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], name="MA20", line=dict(width=1, color='orange')), row=1, col=1)

    # 布林
    fig.add_trace(go.Scatter(x=df.index, y=df['UB'], line=dict(width=0), showlegend=False, hoverinfo='skip'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['LB'], fill='tonexty', fillcolor='rgba(173,216,230,0.1)', line=dict(width=0), name="布林通道"), row=1, col=1)

    # 九轉 (優化：只顯示數字 1, 9 或轉折點以節省渲染)
    b, s = calculate_td_fast(df)
    for i in range(len(df)):
        if b[i] == 9: fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text="9", showarrow=False, yshift=-10, font=dict(color="green", size=12), row=1, col=1)
        if s[i] == 9: fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text="9", showarrow=False, yshift=10, font=dict(color="red", size=12), row=1, col=1)

    # 成交量
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color='gray', opacity=0.5), row=2, col=1)

    fig.update_layout(
        height=600, # 降低高度減少 GPU 負擔
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=10, r=10, t=30, b=10),
        template="plotly_white"
    )
    
    # 關鍵：移除無效日期以提升流暢度
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])

    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
else:
    st.info("請輸入代號並等待資料下載")
