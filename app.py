import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面基礎設定
st.set_page_config(page_title="台美股 Pro 專業版", layout="wide")

# --- 初始化狀態與回調函數 ---
if 'symbol_key' not in st.session_state:
    st.session_state.symbol_key = "2330"
if 'market_key' not in st.session_state:
    st.session_state.market_key = "台股"

def quick_select(s, m):
    st.session_state.symbol_key = s
    st.session_state.market_key = m

# 2. 【側邊欄控制區】
with st.sidebar:
    st.header("📊 專業指標配置")

    st.subheader("🚀 快速選股")
    col1, col2 = st.columns(2)
    with col1:
        st.button("2330 台積電", on_click=quick_select, args=("2330", "台股"), use_container_width=True)
        st.button("TSM (美股)", on_click=quick_select, args=("TSM", "美股"), use_container_width=True)
    with col2:
        st.button("TSLA 特斯拉", on_click=quick_select, args=("TSLA", "美股"), use_container_width=True)
        st.button("MSFT 微軟", on_click=quick_select, args=("MSFT", "美股"), use_container_width=True)

    st.divider()

    market = st.radio("市場切換", ["台股", "美股"], key="market_key", horizontal=True)
    symbol = st.text_input("代號輸入", key="symbol_key").upper()

    range_map = {"三個月": "3mo", "六個月": "6mo", "一年": "1y", "五年": "5y"}
    selected_range = st.selectbox("回推範圍", list(range_map.keys()), index=0)

    st.subheader("均線設定 (MA)")
    ma_cols = st.columns(2)
    with ma_cols[0]:
        show_ma5 = st.toggle("MA 5", value=True)
        show_ma20 = st.toggle("MA 20", value=True)
    with ma_cols[1]:
        show_ma10 = st.toggle("MA 10", value=False)
        show_ma60 = st.toggle("MA 60", value=False)

    st.subheader("技術指標")
    show_td = st.toggle("神奇九轉 (1-9)", value=True)
    show_bb = st.toggle("布林通道 (BB)", value=True)
    show_macd = st.toggle("MACD (紅漲綠跌)", value=True)
    show_kd = st.toggle("KD (隨機指標)", value=True) # 新增 KD 開關
    show_rsi = st.toggle("RSI", value=True)

# 3. 資料抓取與指標計算
@st.cache_data(ttl=600)
def get_processed_data(symbol, market, period):
    s = f"{symbol}.TW" if market == "台股" else symbol
    ticker = yf.Ticker(s)
    df = ticker.history(period=period, interval="1d")
    
    if df.empty and market == "台股":
        s = f"{symbol}.TWO"
        ticker = yf.Ticker(s)
        df = ticker.history(period=period, interval="1d")
        
    if df.empty: return None, "未知股票"

    stock_name = ticker.info.get('longName') or ticker.info.get('shortName') or symbol
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # MA 計算
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

    # KD 計算 (9, 3, 3)
    low_9 = df['Low'].rolling(window=9).min()
    high_9 = df['High'].rolling(window=9).max()
    rsv = 100 * ((df['Close'] - low_9) / (high_9 - low_9))
    df['K'] = rsv.ewm(com=2, adjust=False).mean() # 這裡使用 ewm (com=2 等同於 3日平滑)
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    return df, stock_name

def calc_td_full(df):
    close = df['Close'].values
    buy_s, sell_s = [0]*len(df), [0]*len(df)
    cb, cs = 0, 0
    for i in range(4, len(df)):
        if close[i] < close[i-4]: cb += 1; buy_s[i] = cb
        else: cb = 0
        if close[i] > close[i-4]: cs += 1; sell_s[i] = cs
        else: cs = 0
    return buy_s, sell_s

# 4. 【主圖表區域】
if symbol:
    data, full_name = get_processed_data(symbol, market, range_map[selected_range])
    
    if data is not None:
        st.subheader(f"📈 {symbol} - {full_name}")
        df = data.tail(400)
        
        # 假日過濾
        dt_all = pd.date_range(start=df.index[0], end=df.index[-1], freq='D')
        dt_obs = [d.strftime("%Y-%m-%d") for d in df.index]
        dt_breaks = [d for d in dt_all.strftime("%Y-%m-%d").tolist() if d not in dt_obs]

        # 動態計算子圖數量
        rows = 2 # 主圖 + 成交量
        if show_macd: rows += 1
        if show_kd: rows += 1
        if show_rsi: rows += 1
        
        # 設定每個圖層的高度比例
        row_h = [0.4, 0.12] # 主圖, 成交量
        if show_macd: row_h.append(0.15)
        if show_kd: row_h.append(0.15)
        if show_rsi: row_h.append(0.15)
        
        fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=row_h)

        # A. 主圖
        fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name="收盤連線", line=dict(color='rgba(150,150,150,0.5)', width=1.5), hoverinfo='skip'), row=1, col=1)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="價格",
                                     increasing_line_color='#FF3333', increasing_fillcolor='#FF3333',
                                     decreasing_line_color='#00AA00', decreasing_fillcolor='#00AA00'), row=1, col=1)
        
        ma_configs = {'MA5': (show_ma5, 'blue'), 'MA10': (show_ma10, 'cyan'), 'MA20': (show_ma20, 'orange'), 'MA60': (show_ma60, 'green')}
        for ma_label, (show, color) in ma_configs.items():
            if show: fig.add_trace(go.Scatter(x=df.index, y=df[ma_label], name=ma_label, line=dict(width=1.2, color=color)), row=1, col=1)
        
        if show_bb:
            fig.add_trace(go.Scatter(x=df.index, y=df['UB'], name="布林上", line=dict(color='rgba(173,216,230,0.6)', width=1, dash='dot')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['LB'], name="布林下", line=dict(color='rgba(173,216,230,0.6)', width=1, dash='dot')), row=1, col=1)

        if show_td:
            b, s = calc_td_full(df)
            for i in range(len(df)):
                if 0 < b[i] <= 9: fig.add_annotation(x=df.index[i], y=df['Low'].iloc[i], text=str(b[i]), showarrow=False, yshift=-12, font=dict(color="#00AA00", size=10, family="Arial Black"), row=1, col=1)
                if 0 < s[i] <= 9: fig.add_annotation(x=df.index[i], y=df['High'].iloc[i], text=str(s[i]), showarrow=False, yshift=12, font=dict(color="#FF3333", size=10, family="Arial Black"), row=1, col=1)

        # B. 成交量
        v_colors = ['#FF3333' if c >= o else '#00AA00' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color=v_colors), row=2, col=1)

        curr = 3
        # C. MACD
        if show_macd:
            hist_colors = ['#FF3333' if val >= 0 else '#00AA00' for val in df['Hist']]
            fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name="MACD", line=dict(color='blue', width=1.2)), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Sig'], name="DIF", line=dict(color='orange', width=1.2)), row=curr, col=1)
            fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name="MACD柱", marker_color=hist_colors), row=curr, col=1)
            curr += 1

        # D. KD (隨機指標)
        if show_kd:
            fig.add_trace(go.Scatter(x=df.index, y=df['K'], name="K值", line=dict(color='blue', width=1.2)), row=curr, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['D'], name="D值", line=dict(color='orange', width=1.2)), row=curr, col=1)
            fig.add_hline(y=80, line_dash="dash", line_color="#FF3333", opacity=0.5, row=curr, col=1)
            fig.add_hline(y=20, line_dash="dash", line_color="#00AA00", opacity=0.5, row=curr, col=1)
            curr += 1

        # E. RSI
        if show_rsi:
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='purple', width=1.2)), row=curr, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="#FF3333", opacity=0.5, row=curr, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="#00AA00", opacity=0.5, row=curr, col=1)

        fig.update_layout(height=1000, # 增加總高度以容納更多指標
                          xaxis_rangeslider_visible=True, xaxis_rangeslider_thickness=0.03,
                          hovermode="x unified", template="plotly_white", margin=dict(l=10, r=10, t=30, b=10),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        fig.update_xaxes(rangebreaks=[dict(values=dt_breaks)], showspikes=True, spikemode="across")
        
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True, 'doubleClick': 'reset+autosize'})
    else:
        st.error("查無資料，請確認代號是否正確")
