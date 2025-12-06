import streamlit as st

import pandas as pd

import numpy as np

import requests

import time



# --- 页面配置 ---

st.set_page_config(

    page_title="OKX Kelly Calculator",

    page_icon="🟦",

    layout="centered"

)



# --- 核心函数：获取 OKX 实时价格 ---

# 使用 st.cache_data 防止每次点击按钮都疯狂请求 API，设置 ttl 为 5 秒过期

@st.cache_data(ttl=5)

def get_okx_price(symbol):

    """

    调用 OKX V5 Public API 获取永续合约价格

    """

    inst_id = f"{symbol.upper()}-USDT-SWAP" # 默认拼接为 USDT 永续

    url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"

    

    try:

        response = requests.get(url, timeout=5)

        data = response.json()

        if data['code'] == '0':

            return float(data['data'][0]['last'])

        else:

            return None

    except Exception as e:

        return None



# --- 侧边栏：参数设置 ---

st.sidebar.header("⚙️ 账户与风控")

balance = st.sidebar.number_input("账户可用余额 (USDT)", value=10000.0, step=100.0)



# 胜率与盈亏比

col_s1, col_s2 = st.sidebar.columns(2)

with col_s1:

    win_rate = st.number_input("胜率 (%)", value=51.0, step=0.5) / 100

with col_s2:

    rr_ratio = st.number_input("盈亏比 (R:R)", value=1.5, step=0.1)



# 凯利系数

st.sidebar.markdown("---")

kelly_fraction = st.sidebar.select_slider(

    "凯利激进程度",

    options=[0.1, 0.2, 0.25, 0.5, 1.0],

    value=0.25,

    format_func=lambda x: f"1/{int(1/x)} Kelly" if x < 1 else "Full Kelly"

)

friction = st.sidebar.number_input("预估磨损 (手续费+滑点 %)", value=0.1, step=0.01) / 100



# --- 主界面 ---

st.title("🟦 OKX 动态仓位计算器")

st.caption("Connected to OKX V5 API (USDT-SWAP)")



# 1. 币种与价格获取

col_input, col_price = st.columns([1, 1])



with col_input:

    symbol = st.text_input("输入币种 (如 BTC, ETH, SOL)", value="ETH").upper()

    refresh = st.button("🔄 刷新价格")



# 获取价格逻辑

current_price = get_okx_price(symbol)



with col_price:

    if current_price:

        st.metric(label=f"{symbol}/USDT 永续现价", value=f"${current_price:,.2f}")

    else:

        st.error("无法获取价格，请检查网络或币种")

        # 如果API失败，允许手动输入

        current_price = st.number_input("手动输入入场价", value=0.0)



# 2. 止损设置 (核心交互优化)

st.markdown("### 🛑 止损设置")

st.info("不再需要计算百分比，直接输入你的**心理止损价**即可。")



stop_loss_price = st.number_input(

    f"设定 {symbol} 止损价格", 

    value=current_price * 0.98 if current_price else 0.0, # 默认给个2%的距离

    step=0.1,

    format="%.2f"

)



# --- 核心计算逻辑 ---

if current_price > 0 and stop_loss_price > 0:

    # 自动计算止损百分比 (方向自动识别：做多或做空)

    if stop_loss_price < current_price:

        direction = "🟢 做多 (Long)"

        sl_pct = (current_price - stop_loss_price) / current_price

    else:

        direction = "🔴 做空 (Short)"

        sl_pct = (stop_loss_price - current_price) / current_price

    

    # 防止分母为0或止损太近

    if sl_pct < 0.001:

        st.warning("止损距离太近，无法计算有效仓位。")

        st.stop()



    # --- 凯利公式计算 (复用之前的逻辑) ---

    real_rr = (rr_ratio - friction) / (1 + friction)

    

    if real_rr <= 0:

        raw_kelly = 0

    else:

        raw_kelly = (real_rr * win_rate - (1 - win_rate)) / real_rr



    risk_per_trade_pct = max(0, raw_kelly * kelly_fraction)

    

    # 金额计算

    risk_amount = balance * risk_per_trade_pct # 愿意亏损金额

    position_size = risk_amount / sl_pct # 开仓名义价值

    qty_coin = position_size / current_price # 对应的币数量

    leverage = position_size / balance # 实际杠杆



    # --- 结果展示面板 ---

    st.divider()

    st.subheader(f"📊 计算结果: {direction}")

    

    # 关键大指标

    c1, c2, c3 = st.columns(3)

    c1.metric("建议开仓数量", f"{qty_coin:.3f} {symbol}")

    c2.metric("开仓总价值 (USDT)", f"${position_size:,.0f}")

    c3.metric("实际杠杆倍数", f"{leverage:.2f}x", delta_color="inverse" if leverage > 5 else "normal")



    # 详细风控数据

    with st.expander("查看风控详情 (Risk Details)", expanded=True):

        st.write(f"**止损幅度:** {sl_pct*100:.2f}% (距离 ${abs(current_price-stop_loss_price):.2f})")

        st.write(f"**单笔最大亏损:** ${risk_amount:.2f} (账户的 {risk_per_trade_pct*100:.2f}%)")

        

        if raw_kelly <= 0:

            st.error("根据凯利公式，当前胜率和盈亏比期望值为负，建议**空仓**！")

        elif leverage > 10:

             st.error(f"⚠️ **极高风险**：计算杠杆超过 10倍。建议调低凯利系数或手动减少仓位。")

        elif leverage > 5:

             st.warning(f"⚠️ **高风险**：杠杆超过 5倍，请注意防范插针风险。")

        else:

            st.success("✅ **安全仓位**：风控合理。")



else:

    st.info("等待输入价格数据...")
