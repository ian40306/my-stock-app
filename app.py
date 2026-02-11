import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 頁面設定
st.set_page_config(page_title="台美股 Pro 分析", layout="wide")

# --- 核心邏輯：神奇九轉 (TD Sequential) ---
def calculate_td(df):
    close = df['Close'].values.flatten()
    buy_setup, sell_setup = [0]*len(close), [0]*len(close)
    c_buy, c_sell = 0, 0
    for i in range(4, len(close)):
        if close[i] < close[i-4]:
            c_buy += 1
            buy_setup[i] = c_buy
        else: c_buy = 0
        
        if close[i] > close[i-4]:
            c_sell += 1
            sell_setup[i] = c_sell
        else: c_sell = 0
    return buy_setup, sell_setup

# --- 側邊欄控制 ---
st.sidebar.header("📊 參數設定")
market = st.sidebar.radio("市場", ["台股 (TW)", "美股 (US)"])
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股 (TW)" else "TSLA").upper()
period = st.sidebar.selectbox("時段", ["1mo", "3mo", "1y", "5y"], index=2)

st.sidebar.subheader("技術指標")
show_td = st.sidebar.checkbox("顯示神奇九轉 (TD)", value=True)
show_bb = st.sidebar.checkbox("布林通道 (BB)", value=True)
show_rsi = st.sidebar.checkbox("RSI (14)", value=True)
ma_list = st.sidebar.multiselect("均線", [5, 10, 20, 60], default=[20])

@st.cache_data(ttl=3600)
def fetch_data(symbol, market, period):
    ticker_str = f"{symbol}.TW" if market == "台股 (TW)" else symbol
    t = yf.Ticker(ticker_str)
    df = t.history(period=period)
    if df.empty and market == "台股 (TW)":
        t = yf.Ticker(f"{symbol}.TWO")
        df = t.history(period=period)
    return df, t.info

try:
    df_raw, info = fetch_data(symbol, market, period)
    if not df_raw.empty:
        df = df_raw.copy()
        
        # --- 計算指標 ---
        # 1. 均線
        for ma in ma_list:
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        # 2. 布林通道
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Mid'] + (std * 2)
        df['BB_Lower'] = df['BB_Mid'] - (std * 2)
        
        # 3. RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 4. MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD'] - df['Signal']

        # --- 建立 Plotly 多圖表 ---
        # 修正：使用 row_heights 確保相容性
        rows = 4 if show_rsi else 3
        rh = [0.5, 0.15, 0.15, 0.2] if show_rsi else [0.6, 0.2, 0.2]
        
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=True, 
            vertical_spacing=0.03, 
            row_heights=rh
        )

        # 1. 主圖：K線
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="K線", increasing_line_color='red', decreasing_line_color='green'
        ), row=1, col=1)

        # 均線
        for ma in ma_list:
            fig.add_trace(go.Scatter(x=df.index, y=df[f'MA{ma}'], name=f"MA{ma}", line=dict(width=1)), row=1, col=1)

        # 布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.4)', width=1), name="布林上軌", showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.4)', width=1), fill='tonexty', name="布林通道", showlegend=True), row=1, col=1)

        # 神奇九轉 (TD) 標註
        if show_td:
            buy_s, sell_s = calculate_td(df)
            for i in range(len(df)):
                if 0 < buy_s[i] <= 9:
                    fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text=str(buy_s[i]), showarrow=False, yshift=-15, font=dict(color="green", size=10), row=1, col=1)
                if 0 < sell_s[i] <= 9:
                    fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text=str(sell_s[i]), showarrow=False, yshift=15, font=dict(color="red", size=10), row=1, col=1)

        # 2. 成交量
        colors = ['red' if c >= o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)

        # 3. MACD
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue', width=1), name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange', width=1), name="Signal"), row=3, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Hist'], marker_color='gray', name="MACD柱"), row=3, col=1)

        # 4. RSI
        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1), name="RSI"), row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

        # 佈局優化
        fig.update_layout(
            height=1000,
            xaxis_rangeslider_visible=False,
            hovermode="x unified",
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.title(f"{symbol} - {info.get('longName', '股票分析')}")
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.error("查無資料")
except Exception as e:
    st.error(f"發生錯誤: {e}")
