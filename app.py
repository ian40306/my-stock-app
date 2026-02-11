import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 頁面配置優化
st.set_page_config(page_title="台美股秒開版", layout="wide")

# --- 核心邏輯：神奇九轉 (加上快取防止重複計算) ---
@st.cache_data
def calculate_td(df_close):
    close = df_close.values.flatten()
    buy_setup, sell_setup = [0]*len(close), [0]*len(close)
    c_buy, c_sell = 0, 0
    for i in range(4, len(close)):
        if close[i] < close[i-4]:
            c_buy += 1; buy_setup[i] = c_buy
        else: c_buy = 0
        if close[i] > close[i-4]:
            c_sell += 1; sell_setup[i] = c_sell
        else: c_sell = 0
    return buy_setup, sell_setup

# --- 資料抓取優化 (固定抓取最大範圍並快取) ---
@st.cache_data(ttl=3600, show_spinner=False)
def get_full_data(symbol, market, interval):
    ticker_str = f"{symbol}.TW" if market == "台股 (TW)" else symbol
    t = yf.Ticker(ticker_str)
    # 固定抓 5y，切換範圍時直接從這裡切，不用重新下載
    df = t.history(period="5y", interval=interval)
    if df.empty and market == "台股 (TW)":
        t = yf.Ticker(f"{symbol}.TWO")
        df = t.history(period="5y", interval=interval)
    return df, t.info

# --- 側邊欄 ---
st.sidebar.header("🚀 效能優化看盤")
market = st.sidebar.radio("市場", ["台股 (TW)", "美股 (US)"], horizontal=True)
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股 (TW)" else "NVDA").upper()

cycle_map = {"日線": "1d", "週線": "1wk", "月線": "1mo"}
selected_cycle = st.sidebar.selectbox("K線週期", list(cycle_map.keys()), index=0)

range_map = {
    "一個月": 22, "兩個月": 44, "三個月": 66, 
    "六個月": 132, "一年": 252, "三年": 756, "五年": 1260
}
selected_range_label = st.sidebar.selectbox("顯示範圍", list(range_map.keys()), index=2)

st.sidebar.subheader("指標開關")
show_td = st.sidebar.toggle("神奇九轉", value=True)
show_bb = st.sidebar.toggle("布林通道", value=True)
show_macd = st.sidebar.toggle("MACD", value=True)
show_rsi = st.sidebar.toggle("RSI", value=True)
ma_list = st.sidebar.multiselect("均線", [5, 10, 20, 60], default=[5, 20])

try:
    # 1. 抓取資料 (快取層)
    full_df, info = get_full_data(symbol, market, cycle_map[selected_cycle])
    
    if not full_df.empty:
        # 2. 根據選擇範圍截取資料 (記憶體操作，極快)
        num_days = range_map[selected_range_label]
        df = full_df.tail(num_days).copy()
        
        # 3. 指標計算 (僅計算顯示範圍，加速)
        for ma in ma_list:
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Mid'] + (std * 2)
        df['BB_Lower'] = df['BB_Mid'] - (std * 2)
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_val'] = exp1 - exp2
        df['Signal'] = df['MACD_val'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD_val'] - df['Signal']

        # 4. 繪圖優化
        rows = 2 + (1 if show_macd else 0) + (1 if show_rsi else 0)
        rh = [0.5, 0.15] + ([0.15] if show_macd else []) + ([0.15] if show_rsi else [])
        
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=rh)

        # 背景趨勢線
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="收盤連線", line=dict(color='rgba(128,128,128,0.2)', width=1), hoverinfo='skip'), row=1, col=1)

        # K線 (WebGL 加速建議用 go.Candlestick，但資料量小於 1000 根時原本就很快)
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="價格", increasing_line_color='#FF3333', decreasing_line_color='#00AA00'
        ), row=1, col=1)

        for ma in ma_list:
            fig.add_trace(go.Scatter(x=df.index, y=df[f'MA{ma}'], name=f"MA{ma}", line=dict(width=1.2)), row=1, col=1)

        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173,216,230,0.4)', width=1), name="布林上軌"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173,216,230,0.4)', width=1), fill='tonexty', fillcolor='rgba(173,216,230,0.05)', name="布林下軌"), row=1, col=1)

        if show_td:
            b, s = calculate_td(df['Close'])
            for i in range(len(df)):
                if 0 < b[i] <= 9: fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text=str(b[i]), showarrow=False, yshift=-12, font=dict(color="#00AA00", size=9), row=1, col=1)
                if 0 < s[i] <= 9: fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text=str(s[i]), showarrow=False, yshift=12, font=dict(color="#FF3333", size=9), row=1, col=1)

        # 2. 成交量
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=['#FF3333' if c >= o else '#00AA00' for c, o in zip(df['Close'], df['Open'])], name="成交量"), row=2, col=1)

        curr = 3
        if show_macd:
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_val'], name="MACD", line=dict(color='blue', width=1)), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], name="Signal", line=dict(color='orange', width=1)), row=curr, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name="MACD柱", marker_color='gray'), row=curr, col=1)
            curr += 1

        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='purple', width=1)), row=curr, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=curr, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=curr, col=1)

        fig.update_layout(
            height=800, xaxis_rangeslider_visible=False, hovermode="x unified",
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            template="plotly_white"
        )
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showspikes=True, spikemode="across", spikethickness=1, spikedash="solid", spikecolor="gray")
        
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    else: st.error("查無資料")
except Exception as e: st.error(f"分析失敗: {e}")
