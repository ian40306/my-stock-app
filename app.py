import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="台美股 Pro 移動分析系統", layout="wide")

# --- 核心邏輯：神奇九轉 ---
def calculate_td(df):
    close = df['Close'].values.flatten()
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

# --- 側邊欄控制 ---
st.sidebar.header("📊 投資分析儀表板")
market = st.sidebar.radio("選擇市場", ["台股 (TW)", "美股 (US)"])
symbol = st.sidebar.text_input("輸入代號", value="2330" if market == "台股 (TW)" else "NVDA").upper()

# 週期切換 (K線單位)
cycle_map = {"日線": "1d", "週線": "1wk", "月線": "1mo"}
selected_cycle = st.sidebar.selectbox("K線週期", list(cycle_map.keys()), index=0)

# 回推時間範圍 (預設三個月)
range_map = {
    "一個月": "1mo", "兩個月": "2mo", "三個月": "3mo", 
    "六個月": "6mo", "一年": "1y", "三年": "3y", "五年": "5y"
}
selected_range = st.sidebar.selectbox("回推時間範圍", list(range_map.keys()), index=2)

st.sidebar.subheader("技術指標顯示")
show_td = st.sidebar.checkbox("顯示神奇九轉 (TD)", value=True)
show_bb = st.sidebar.checkbox("顯示布林通道 (BB)", value=True)
show_macd = st.sidebar.checkbox("顯示 MACD", value=True)
show_rsi = st.sidebar.checkbox("顯示 RSI (14)", value=True)
ma_list = st.sidebar.multiselect("均線 MA", [5, 10, 20, 60], default=[5, 20])

@st.cache_data(ttl=3600)
def fetch_stock_data(symbol, market, interval, period):
    ticker_str = f"{symbol}.TW" if market == "台股 (TW)" else symbol
    t = yf.Ticker(ticker_str)
    # 這裡抓取對應的回推天數資料
    df = t.history(period=period, interval=interval)
    if df.empty and market == "台股 (TW)":
        t = yf.Ticker(f"{symbol}.TWO")
        df = t.history(period=period, interval=interval)
    return df, t.info

try:
    df_raw, info = fetch_stock_data(symbol, market, cycle_map[selected_cycle], range_map[selected_range])
    if not df_raw.empty:
        df = df_raw.copy()
        
        # 指標計算
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

        # 子圖高度配置
        rows = 2
        if show_macd: rows += 1
        if show_rsi: rows += 1
        rh = [0.5, 0.15]
        if show_macd: rh.append(0.15)
        if show_rsi: rh.append(0.15)
        
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=rh)

        # 1. 主圖：收盤連線 (底部背景)
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="收盤連線", line=dict(color='rgba(128,128,128,0.2)', width=1)), row=1, col=1)

        # 2. 主圖：K線
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="價格", increasing_line_color='#FF3333', decreasing_line_color='#00AA00'
        ), row=1, col=1)

        # 均線
        for ma in ma_list:
            fig.add_trace(go.Scatter(x=df.index, y=df[f'MA{ma}'], name=f"MA{ma}", line=dict(width=1.2)), row=1, col=1)

        # 布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173,216,230,0.5)', width=1), name="布林上軌"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173,216,230,0.5)', width=1), fill='tonexty', fillcolor='rgba(173,216,230,0.1)', name="布林下軌"), row=1, col=1)

        # 神奇九轉標註
        if show_td:
            b, s = calculate_td(df)
            for i in range(len(df)):
                if 0 < b[i] <= 9: fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text=str(b[i]), showarrow=False, yshift=-15, font=dict(color="#00AA00", size=10), row=1, col=1)
                if 0 < s[i] <= 9: fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text=str(s[i]), showarrow=False, yshift=15, font=dict(color="#FF3333", size=10), row=1, col=1)

        # 3. 成交量
        v_colors = ['#FF3333' if c >= o else '#00AA00' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=v_colors, name="成交量"), row=2, col=1)

        curr = 3
        if show_macd:
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_val'], name="MACD", line=dict(color='blue')), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], name="Signal", line=dict(color='orange')), row=curr, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name="MACD柱", marker_color='gray'), row=curr, col=1)
            curr += 1

        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='purple')), row=curr, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=curr, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=curr, col=1)

        # --- 佈局優化 ---
        fig.update_layout(
            height=900,
            xaxis_rangeslider_visible=False,
            hovermode="x unified",
            margin=dict(l=10, r=10, t=50, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # 移除假日 & 貫穿虛線
        fig.update_xaxes(
            rangebreaks=[dict(bounds=["sat", "mon"])],
            showspikes=True,
            spikemode="across",
            spikethickness=1,
            spikedash="solid",
            spikecolor="gray"
        )
        
        st.title(f"{symbol} - {info.get('longName', '股票分析')} (週期: {selected_cycle} / 範圍: {selected_range})")
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    else: st.error("查無資料，請確認代號是否正確。")
except Exception as e: st.error(f"資料抓取失敗: {e}")
