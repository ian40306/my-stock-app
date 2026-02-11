import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 1. 頁面基礎設定
st.set_page_config(page_title="極速看盤", layout="wide")

# 2. 側邊欄：精簡選項以減少引發重新計算的次數
st.sidebar.header("🚀 秒開配置")
market = st.sidebar.radio("市場", ["台股", "美股"], horizontal=True)
symbol = st.sidebar.text_input("代號", value="2330" if market == "台股" else "TSLA").upper()

# 限制選擇，減少 iPad 的計算負擔
range_map = {"三個月": "3mo", "六個月": "6mo", "一年": "1y", "五年": "5y"}
selected_range = st.sidebar.selectbox("回推範圍", list(range_map.keys()), index=0)

# 3. 極速下載與處理
@st.cache_data(ttl=600)
def get_data_fast(symbol, market, period):
    s = f"{symbol}.TW" if market == "台股" else symbol
    # 增加 threads=False 避免某些環境下的衝突，progress=False 減少 log 輸出
    df = yf.download(s, period=period, interval="1d", progress=False, threads=False)
    
    if df.empty and market == "台股":
        df = yf.download(f"{symbol}.TWO", period=period, interval="1d", progress=False)
        
    if not df.empty:
        # 修正新版 yfinance 的欄位名稱問題
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    return df

# 4. 繪圖邏輯優化
def draw_chart(df, symbol):
    # 只計算最核心指標
    df['MA20'] = df['Close'].rolling(20).mean()
    std = df['Close'].rolling(20).std()
    df['UB'] = df['MA20'] + (std * 2)
    df['LB'] = df['MA20'] - (std * 2)
    
    # 使用 Light 模板減少渲染負擔
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.05, row_heights=[0.7, 0.3])

    # K線
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        name="K線", increasing_line_color='#FF3333', decreasing_line_color='#00AA00'
    ), row=1, col=1)

    # 布林通道 (僅畫線，不填充色以加快渲染)
    fig.add_trace(go.Scatter(x=df.index, y=df['UB'], line=dict(color='rgba(173,216,230,0.5)', width=1), name="布林上軌"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['LB'], line=dict(color='rgba(173,216,230,0.5)', width=1), name="布林下軌"), row=1, col=1)

    # 成交量
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name="成交量", marker_color='gray'), row=2, col=1)

    fig.update_layout(
        height=550, # iPad 最佳高度，不需滾動
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        margin=dict(l=5, r=5, t=30, b=5),
        template="plotly_white",
        showlegend=False
    )
    
    # 移除斷點 (非交易日)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    return fig

# --- 主程式執行 ---
if symbol:
    with st.spinner('連線中...'):
        data = get_data_fast(symbol, market, range_map[selected_range])
        
    if not data.empty:
        # 效能關鍵：如果資料量太大（如5年日線），在 iPad 上只繪製最後 300 根
        display_df = data.tail(300) if len(data) > 300 else data
        
        fig = draw_chart(display_df, symbol)
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        # 數據顯示改用更輕量的 table
        st.caption(f"最後更新時間: {data.index[-1].strftime('%Y-%m-%d')}")
    else:
        st.warning("查無資料，請輸入正確代號 (例如: 2330 或 AAPL)")
