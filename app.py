import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面基礎設定
st.set_page_config(page_title="台美股 Pro 極速版", layout="wide")

# 2. 側邊欄：配置
st.sidebar.header("📊 專業指標配置")
market = st.sidebar.radio("市場", ["台股", "美股"], horizontal=True)
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股" else "NVDA").upper()

range_map = {"三個月": "3mo", "六個月": "6mo", "一年": "1y", "五年": "5y"}
selected_range = st.sidebar.selectbox("回推範圍", list(range_map.keys()), index=0)

# 指標開關 (全部改為 Toggle 按鈕)
st.sidebar.subheader("均線設定 (MA)")
show_ma5 = st.sidebar.toggle("MA 5", value=True)
show_ma10 = st.sidebar.toggle("MA 10", value=False)
show_ma20 = st.sidebar.toggle("MA 20", value=True)
show_ma60 = st.sidebar.toggle("MA 60", value=False)

st.sidebar.subheader("技術指標")
show_td = st.sidebar.toggle("神奇九轉 (TD)", value=True)
show_bb = st.sidebar.toggle("布林通道 (BB)", value=True)
show_macd = st.sidebar.toggle("MACD", value=True)
show_rsi = st.sidebar.toggle("RSI", value=True)

# 3. 極速下載與快取處理
@st.cache_data(ttl=600)
def get_processed_data(symbol, market, period):
    s = f"{symbol}.TW" if market == "台股" else symbol
    df = yf.download(s, period=period, interval="1d", progress=False, threads=False)
    
    if df.empty and market == "台股":
        df = yf.download(f"{symbol}.TWO", period=period, interval="1d", progress=False)
        
    if df.empty: return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 計算均線
    for ma in [5, 10, 20, 60]:
        df[f'MA{ma}'] = df['Close'].rolling(ma).mean()
    
    # 布林
    std = df['Close'].rolling(20).std()
    df['UB'] = df['MA20'] + (std * 2)
    df['LB'] = df['MA20'] - (std * 2)
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))

    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Sig'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Sig']
    
    return df

# 九轉計算邏輯 (高效版)
def calc_td_9(df):
    close = df['Close'].values
    buy_s, sell_s = [0]*len(df), [0]*len(df)
    cb, cs = 0, 0
    for i in range(4, len(df)):
        if close[i] < close[i-4]: cb += 1; buy_s[i] = cb
        else: cb = 0
        if close[i] > close[i-4]: cs += 1; sell_s[i] = cs
        else: cs = 0
    return buy_s, sell_s

# 4. 主程式執行
if symbol:
    data = get_processed_data(symbol, market, range_map[selected_range])
    
    if data is not None:
        df = data.tail(500) # 限制繪圖點數確保 iPad 流暢
        
        rows = 2 
        if show_macd: rows += 1
        if show_rsi: rows += 1
        rh = [0.4, 0.15]
        if show_macd: rh.append(0.15)
        if show_rsi: rh.append(0.15)
        
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=rh)

        # --- A. 主圖層 ---
        # 1. 每天收盤價連線 (置底)
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="收盤連線", 
                                line=dict(color='rgba(100,100,100,0.3)', width=1.5), 
                                hoverinfo='skip'), row=1, col=1)
        
        # 2. K線圖
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="價格"), row=1, col=1)
        
        # 3. 均線開關控制
        ma_configs = {
            'MA5': (show_ma5, 'blue'),
            'MA10': (show_ma10, 'cyan'),
            'MA20': (show_ma20, 'orange'),
            'MA60': (show_ma60, 'green')
        }
        for ma_label, (show, color) in ma_configs.items():
            if show:
                fig.add_trace(go.Scatter(x=df.index, y=df[ma_label], name=ma_label, line=dict(width=1.2, color=color)), row=1, col=1)
        
        # 4. 布林通道
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['UB'], name="布林上", line=dict(color='rgba(173,216,230,0.5)', width=1, dash='dash')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['LB'], name="布林下", line=dict(color='rgba(173,216,230,0.5)', width=1, dash='dash')), row=1, col=1)

        # 5. 神奇九轉 (標註 9)
        if show_td:
            b, s = calc_td_9(df)
            for i in range(len(df)):
                if b[i] == 9: fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text="9", showarrow=False, yshift=-12, font=dict(color="green", size=12,强调=True), row=1, col=1)
                if s[i] == 9: fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text="9", showarrow=False, yshift=12, font=dict(color="red", size=12), row=1, col=1)

        # --- B. 成交量 ---
        v_colors = ['red' if c >= o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=v_colors), row=2, col=1)

        curr = 3
        # --- C. MACD ---
        if show_macd:
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name="MACD", line=dict(color='blue', width=1)), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Sig'], name="訊號線", line=dict(color='orange', width=1)), row=curr, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name="MACD柱", marker_color='gray'), row=curr, col=1)
            curr += 1

        # --- D. RSI ---
        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='purple', width=1)), row=curr, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=curr, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=curr, col=1)

        # 佈局優化 (包含雙擊還原與滑桿)
        fig.update_layout(
            height=850,
            xaxis_rangeslider_visible=True,
            xaxis_rangeslider_thickness=0.03,
            hovermode="x unified",
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showspikes=True, spikemode="across", spikedash="solid", spikecolor="#D3D3D3", spikethickness=1)
        
        st.plotly_chart(fig, use_container_width=True, config={
            'scrollZoom': True,
            'displayModeBar': True,
            'doubleClick': 'reset+autosize' # 雙擊還原
        })
        
    else:
        st.error("查無資料")
