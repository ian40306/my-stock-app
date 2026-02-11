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

# 均線選項回歸
ma_options = st.sidebar.multiselect("均線 (MA)", [5, 10, 20, 60], default=[5, 20])

# 指標快速開關
st.sidebar.subheader("指標顯示")
show_bb = st.sidebar.toggle("布林通道", value=True)
show_macd = st.sidebar.toggle("MACD", value=True)
show_rsi = st.sidebar.toggle("RSI", value=True)

# 3. 極速下載與快取
@st.cache_data(ttl=600)
def get_processed_data(symbol, market, period):
    s = f"{symbol}.TW" if market == "台股" else symbol
    df = yf.download(s, period=period, interval="1d", progress=False, threads=False)
    
    if df.empty and market == "台股":
        df = yf.download(f"{symbol}.TWO", period=period, interval="1d", progress=False)
        
    if df.empty: return None

    # 修正 yfinance 欄位
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 預先計算所有可能需要的 MA
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

# 4. 主程式執行
if symbol:
    data = get_processed_data(symbol, market, range_map[selected_range])
    
    if data is not None:
        # 效能關鍵：iPad 繪圖限制在 500 點以內
        df = data.tail(500)
        
        # 動態計算子圖
        rows = 2 
        if show_macd: rows += 1
        if show_rsi: rows += 1
        
        rh = [0.4, 0.15]
        if show_macd: rh.append(0.15)
        if show_rsi: rh.append(0.15)
        
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.03, row_heights=rh)

        # A. 主圖
        # 收盤連線
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="連線", line=dict(color='rgba(128,128,128,0.2)', width=1), hoverinfo='skip'), row=1, col=1)
        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="價格"), row=1, col=1)
        
        # 繪製選中的均線
        colors = {5: 'blue', 10: 'cyan', 20: 'orange', 60: 'green'}
        for ma in ma_options:
            fig.add_trace(go.Scatter(x=df.index, y=df[f'MA{ma}'], name=f"MA{ma}", line=dict(width=1, color=colors[ma])), row=1, col=1)
        
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['UB'], name="布林上", line=dict(color='rgba(173,216,230,0.6)', width=1, dash='dot')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['LB'], name="布林下", line=dict(color='rgba(173,216,230,0.6)', width=1, dash='dot')), row=1, col=1)

        # B. 成交量
        v_colors = ['red' if c >= o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=v_colors), row=2, col=1)

        curr = 3
        # C. MACD
        if show_macd:
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name="MACD線", line=dict(color='blue', width=1.2)), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Sig'], name="訊號線", line=dict(color='orange', width=1)), row=curr, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name="MACD柱", marker_color='gray'), row=curr, col=1)
            curr += 1

        # D. RSI
        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='purple', width=1.2)), row=curr, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=curr, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=curr, col=1)

        # 佈局優化
        fig.update_layout(
            height=850,
            xaxis_rangeslider_visible=True, # 加回滑桿，方便解決「匡錯回不去」的問題
            xaxis_rangeslider_thickness=0.02, # 讓它薄一點
            hovermode="x unified",
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        # 貫穿線
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], showspikes=True, spikemode="across", spikedash="solid", spikecolor="#D3D3D3", spikethickness=1)
        
        # 顯示圖表並開啟縮放功能
        st.plotly_chart(fig, use_container_width=True, config={
            'scrollZoom': True,           # 開啟滾輪/兩指縮放
            'displayModeBar': True,       # 顯示上方工具列，內有「重設軸線」按鈕
            'modeBarButtonsToRemove': ['select2d', 'lasso2d'] # 移除不需要的工具
        })
        
    else:
        st.error("查無資料，請更換代號")
