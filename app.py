import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 頁面設定
st.set_page_config(page_title="台美股 Pro 分析", layout="wide")

# --- 側邊欄控制 ---
st.sidebar.header("📊 參數設定")
market = st.sidebar.radio("市場", ["台股 (TW)", "美股 (US)"])
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股 (TW)" else "TSLA").upper()
period = st.sidebar.selectbox("時段", ["1mo", "3mo", "1y", "5y"], index=2)

# 技術指標開關
st.sidebar.subheader("技術指標")
show_bb = st.sidebar.checkbox("布林通道 (Bollinger Bands)", value=True)
show_rsi = st.sidebar.checkbox("RSI (相對強弱指標)", value=True)
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
    df, info = fetch_data(symbol, market, period)
    if not df.empty:
        # --- 計算指標 ---
        # 1. 均線
        for ma in ma_list:
            df[f'MA{ma}'] = df['Close'].rolling(window=ma).mean()
        
        # 2. 布林通道 (20日, 2倍標準差)
        df['BB_Mid'] = df['Close'].rolling(window=20).mean()
        std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Mid'] + (std * 2)
        df['BB_Lower'] = df['BB_Mid'] - (std * 2)
        
        # 3. RSI (14日)
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
        # 增加一個子圖給 RSI
        rows = 4 if show_rsi else 3
        fig = make_subplots(
            rows=rows, cols=1, shared_xaxes=True, 
            vertical_spacing=0.05, 
            row_height_ratios=[0.5, 0.15, 0.15, 0.2] if show_rsi else [0.6, 0.2, 0.2]
        )

        # 1. 主圖：K線
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="K線", increasing_line_color='red', decreasing_line_color='green'
        ), row=1, col=1)

        # 收盤連線 (淡淡的灰線)
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', line=dict(color='gray', width=1), opacity=0.3, name="收盤連線"), row=1, col=1)

        # 均線
        for ma in ma_list:
            fig.add_trace(go.Scatter(x=df.index, y=df[f'MA{ma}'], name=f"MA{ma}", line=dict(width=1.5)), row=1, col=1)

        # 布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='rgba(173, 216, 230, 0.4)', width=1), name="布林上軌"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='rgba(173, 216, 230, 0.4)', width=1), fill='tonexty', name="布林下軌"), row=1, col=1)

        # 2. 成交量
        colors = ['red' if c >= o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)

        # 3. MACD
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], line=dict(color='blue', width=1), name="MACD"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Signal'], line=dict(color='orange', width=1), name="Signal"), row=3, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['Hist'], marker_color='gray', opacity=0.5, name="柱狀圖"), row=3, col=1)

        # 4. RSI (如果開啟)
        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=1.5), name="RSI"), row=4, col=1)
            # RSI 70/30 超買超賣線
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=4, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=4, col=1)

        # --- 佈局優化 (iPad 觸控友善) ---
        fig.update_layout(
            height=900,
            title_text=f"{symbol} - {info.get('longName', '')}",
            xaxis_rangeslider_visible=False, # 隱藏下方滑桿以節省空間
            hovermode="x unified", # 手指碰觸時顯示所有指標數值
            margin=dict(l=10, r=10, t=50, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # 基本面小資訊
        col1, col2, col3 = st.columns(3)
        col1.metric("目前股價", f"{df['Close'].iloc[-1]:.2f}", f"{df['Close'].iloc[-1] - df['Close'].iloc[-2]:.2f}")
        col2.metric("最高價 (區間)", f"{df['High'].max():.2f}")
        col3.metric("RSI (14)", f"{df['RSI'].iloc[-1]:.1f}")

    else:
        st.error("查無資料")
except Exception as e:
    st.error(f"發生錯誤: {e}")
