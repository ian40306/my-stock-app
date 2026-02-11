import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 頁面設定
st.set_page_config(page_title="台美股 Pro 移動分析", layout="wide")

# --- 核心邏輯：神奇九轉 ---
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
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股 (TW)" else "NVDA").upper()
period = st.sidebar.selectbox("時段", ["1mo", "3mo", "1y", "5y"], index=2)

st.sidebar.subheader("技術指標")
show_td = st.sidebar.checkbox("顯示神奇九轉 (TD)", value=True)
show_bb = st.sidebar.checkbox("布林通道 (BB)", value=True)
show_macd = st.sidebar.checkbox("顯示 MACD", value=True)
show_rsi = st.sidebar.checkbox("顯示 RSI (14)", value=True)
ma_list = st.sidebar.multiselect("均線", [5, 10, 20, 60], default=[5, 20])

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
        for ma in ma_list:
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        # 布林通道
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Mid'] + (std * 2)
        df['BB_Lower'] = df['BB_Mid'] - (std * 2)
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))

        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_val'] = exp1 - exp2
        df['Signal'] = df['MACD_val'].ewm(span=9, adjust=False).mean()
        df['Hist'] = df['MACD_val'] - df['Signal']

        # --- 建立動態子圖 ---
        # 計算需要多少列
        chart_rows = 2 # K線 + 成交量
        if show_macd: chart_rows += 1
        if show_rsi: chart_rows += 1
        
        # 設定每一列的高度比例
        row_h = [0.5, 0.15] # 預設 K線, 成交量
        if show_macd: row_h.append(0.15)
        if show_rsi: row_h.append(0.15)
        
        fig = make_subplots(
            rows=chart_rows, cols=1, 
            shared_xaxes=True, 
            vertical_spacing=0.02, 
            row_heights=row_h
        )

        # 1. 主圖：K線 (Row 1)
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="K線", increasing_line_color='#FF3333', decreasing_line_color='#00AA00'
        ), row=1, col=1)

        # 均線
        for ma in ma_list:
            fig.add_trace(go.Scatter(x=df.index, y=df[f'MA{ma}'], name=f"MA{ma}", line=dict(width=1.2)), row=1, col=1)

        # 布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.4)', width=0.5), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.4)', width=0.5), fill='tonexty', name="布林通道"), row=1, col=1)

        # 神奇九轉標註
        if show_td:
            buy_s, sell_s = calculate_td(df)
            for i in range(len(df)):
                if 0 < buy_s[i] <= 9:
                    fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text=str(buy_s[i]), showarrow=False, yshift=-12, font=dict(color="#00AA00", size=9), row=1, col=1)
                if 0 < sell_s[i] <= 9:
                    fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text=str(sell_s[i]), showarrow=False, yshift=12, font=dict(color="#FF3333", size=9), row=1, col=1)

        # 2. 成交量 (Row 2)
        v_colors = ['#FF3333' if c >= o else '#00AA00' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=v_colors, name="成交量", opacity=0.8), row=2, col=1)

        current_row = 3
        # 3. MACD (如果開啟)
        if show_macd:
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD_val'], line=dict(color='blue', width=1), name="MACD"), row=current_row, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange', width=1), name="Signal"), row=current_row, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Hist'], marker_color='gray', name="MACD柱"), row=current_row, col=1)
            current_row += 1

        # 4. RSI (如果開啟，放在最後)
        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1.2), name="RSI"), row=current_row, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=current_row, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=current_row, col=1)

        # --- 全域佈局優化 ---
        fig.update_layout(
            height=1000,
            xaxis_rangeslider_visible=False,
            hovermode="x unified", # 關鍵：手指點擊顯示所有圖層數據
            hoverlabel=dict(bgcolor="rgba(255, 255, 255, 0.9)", font_size=12),
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # 強制 Y 軸顯示數值，不重疊
        fig.update_yaxes(tickformat=".2f", row=1, col=1)

        st.title(f"{symbol} - {info.get('longName', '股票分析')}")
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 數據一覽表
        with st.expander("📊 查看最後 5 筆數據"):
            st.table(df.tail(5)[['Open', 'High', 'Low', 'Close', 'Volume']])

    else:
        st.error("查無資料，請檢查代號")
except Exception as e:
    st.error(f"分析失敗: {e}")
