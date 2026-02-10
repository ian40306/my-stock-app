import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as patches

# 設定頁面標題與寬度
st.set_page_config(page_title="台美股 AI 分析助手", layout="wide")

# Mac/iOS 建議字體
plt.rcParams['font.sans-serif'] = ['Heiti TC', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# --- 核心邏輯：神奇九轉 ---
def calculate_td(df):
    close = df['Close'].values.flatten()
    buy_setup, sell_setup = [0]*len(close), [0]*len(close)
    c_buy, c_sell = 0, 0
    for i in range(4, len(close)):
        if close[i] < close[i-4]: c_buy += 1; buy_setup[i] = c_buy
        else: c_buy = 0
        if close[i] > close[i-4]: c_sell += 1; sell_setup[i] = c_sell
        else: c_sell = 0
    return buy_setup, sell_setup

# --- 側邊欄：控制面板 ---
st.sidebar.header("📊 市場控制中心")
market = st.sidebar.radio("選擇市場", ["台股 (TW)", "美股 (US)"])
symbol = st.sidebar.text_input("輸入股票代號", value="2330" if market == "台股 (TW)" else "AAPL").upper()

period_map = {"1個月": "1mo", "2個月": "2mo", "3個月": "3mo", "1年": "1y", "5年": "5y"}
selected_period = st.sidebar.selectbox("時間範圍", list(period_map.keys()), index=3)

st.sidebar.subheader("技術指標")
show_td = st.sidebar.checkbox("顯示神奇九轉", value=True)
ma_options = st.sidebar.multiselect("顯示均線", ["MA5", "MA10", "MA20", "MA60"], default=["MA5", "MA20"])

# --- 資料抓取 ---
@st.cache_data(ttl=3600) # 快取一小時，提升 iPad 載入速度
def get_data(symbol, market, period):
    full_symbol = f"{symbol}.TW" if market == "台股 (TW)" else symbol
    ticker = yf.Ticker(full_symbol)
    data = ticker.history(period=period)
    if data.empty and market == "台股 (TW)":
        ticker = yf.Ticker(f"{symbol}.TWO")
        data = ticker.history(period=period)
    return data, ticker.info

try:
    data, info = get_data(symbol, market, period_map[selected_period])
    
    if not data.empty:
        # 標題顯示
        stock_name = info.get('longName') or info.get('shortName') or symbol
        st.title(f"{symbol} - {stock_name}")
        
        # 繪圖
        fig = plt.figure(figsize=(12, 10))
        gs = gridspec.GridSpec(3, 1, height_ratios=[4, 1, 1], hspace=0.2)
        ax_price = fig.add_subplot(gs[0])
        ax_vol = fig.add_subplot(gs[1], sharex=ax_price)
        ax_macd = fig.add_subplot(gs[2], sharex=ax_price)

        # 準備資料
        df = data.copy().reset_index()
        x = np.arange(len(df))
        opens, closes = df['Open'].values, df['Close'].values
        highs, lows = df['High'].values, df['Low'].values

        # 1. 主圖：K線與收盤連線
        ax_price.plot(x, closes, color='gray', alpha=0.3, linewidth=1)
        for i in range(len(df)):
            color = 'red' if closes[i] >= opens[i] else 'green'
            ax_price.vlines(x[i], lows[i], highs[i], color=color)
            ax_price.add_patch(patches.Rectangle((x[i]-0.3, min(opens[i], closes[i])), 0.6, max(abs(closes[i]-opens[i]), 0.1), color=color))

        for ma in ma_options:
            ax_price.plot(x, df['Close'].rolling(int(ma[2:])).mean(), label=ma)

        if show_td:
            b, s = calculate_td(df)
            for i in range(len(df)):
                if 0 < b[i] <= 9: ax_price.text(i, lows[i]*0.98, str(b[i]), color='green', ha='center', fontsize=8)
                if 0 < s[i] <= 9: ax_price.text(i, highs[i]*1.02, str(s[i]), color='red', ha='center', fontsize=8)
            ax_price.set_ylim(min(lows)*0.95, max(highs)*1.05)

        # 2. 成交量
        ax_vol.bar(x, df['Volume'], color=['red' if c >= o else 'green' for c, o in zip(closes, opens)])
        
        # 3. MACD
        exp1 = df['Close'].ewm(span=12).mean()
        exp2 = df['Close'].ewm(span=26).mean()
        macd = exp1 - exp2
        sig = macd.ewm(span=9).mean()
        ax_macd.plot(x, macd, label='MACD')
        ax_macd.plot(x, sig, label='Signal')
        ax_macd.bar(x, macd-sig, color='gray', alpha=0.3)

        # 格式化日期軸
        ax_price.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, p: df['Date'].iloc[int(v)].strftime('%m/%d') if 0<=v<len(df) else ""))
        ax_price.grid(alpha=0.2); ax_price.legend()
        
        st.pyplot(fig)
        
        # 顯示數值表格
        with st.expander("查看原始數據"):
            st.dataframe(data.tail(10))

    else:
        st.error("找不到該股票資料，請檢查代號是否有誤。")
except Exception as e:
    st.warning(f"請輸入正確的代號以開始分析。")