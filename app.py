import streamlit as st

import requests



# --- 页面全局配置 ---

st.set_page_config(

    page_title="动态仓位计算器",

    page_icon="⚖️",

    layout="wide" # 开启宽屏模式，方便横向对比

)



# --- 核心函数：获取 OKX 实时价格 ---

@st.cache_data(ttl=5)

def get_okx_price(symbol):

    inst_id = f"{symbol.upper()}-USDT-SWAP"

    url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"

    try:

        response = requests.get(url, timeout=5)

        data = response.json()

        if data['code'] == '0':

            return float(data['data'][0]['last'])

        return None

    except:

        return None



# --- 核心函数：凯利计算逻辑 ---

def calculate_kelly_position(balance, win_rate, rr_ratio, friction, kelly_fraction, entry_price, sl_price, leverage_input):

    # 1. 判断方向与止损幅度

    if sl_price < entry_price:

        direction = "long"

        sl_pct = (entry_price - sl_price) / entry_price

    else:

        direction = "short"

        sl_pct = (sl_price - entry_price) / entry_price

    

    # 保护机制：防止止损太近导致除零

    if sl_pct < 0.001:

        return None



    # 2. 凯利公式

    real_rr = (rr_ratio - friction) / (1 + friction)

    if real_rr <= 0:

        raw_kelly = 0

    else:

        raw_kelly = (real_rr * win_rate - (1 - win_rate)) / real_rr

    

    risk_per_trade_pct = max(0, raw_kelly * kelly_fraction)

    

    # 3. 仓位计算

    risk_amount = balance * risk_per_trade_pct # 愿意亏损的金额 (Risk)

    position_value = risk_amount / sl_pct # 名义持仓价值 (Notional Value)

    coin_qty = position_value / entry_price # 币的数量

    

    # 4. 保证金计算 (基于用户输入的杠杆)

    required_margin = position_value / leverage_input

    

    # 5. 实际有效杠杆 (Effective Leverage)

    effective_leverage = position_value / balance



    return {

        "direction": direction,

        "sl_pct": sl_pct,

        "risk_amount": risk_amount,

        "position_value": position_value,

        "coin_qty": coin_qty,

        "required_margin": required_margin,

        "effective_leverage": effective_leverage,

        "raw_kelly": raw_kelly

    }



# ==========================================

# UI 布局开始

# ==========================================



st.title("⚖️ 动态仓位计算器")

st.markdown("Connected to **OKX V5 API** (USDT-SWAP)")



# --- 模块 1：账户与风控 (移至主屏幕顶部) ---

with st.container(border=True):

    st.subheader("🛠️ 账户与风控参数")

    

    # 第一行：资金与杠杆

    c1, c2, c3 = st.columns(3)

    with c1:

        balance = st.number_input("账户可用余额 (USDT)", value=10000.0, step=100.0)

    with c2:

        # 用户要求的自定义杠杆输入

        user_leverage = st.number_input(

            "开单杠杆倍数 (Leverage)", 

            min_value=0.1, 

            max_value=20.0, 

            value=5.0, 

            step=0.1, 

            format="%.2f",

            help="你将在交易所实际调节的杠杆倍数"

        )

    with c3:

        # 凯利激进程度

        kelly_fraction = st.select_slider(

            "凯利激进程度 (Kelly Fraction)",

            options=[0.1, 0.2, 0.25, 0.5, 1.0],

            value=0.25,

            format_func=lambda x: f"1/{int(1/x)} Kelly" if x < 1 else "Full Kelly"

        )



    # 第二行：策略参数

    c4, c5, c6 = st.columns(3)

    with c4:

        win_rate = st.number_input("策略胜率 (%)", value=51.0, step=0.5) / 100

    with c5:

        rr_ratio = st.number_input("目标盈亏比 (R:R)", value=1.5, step=0.1)

    with c6:

        friction = st.number_input("预估磨损 (手续费+滑点 %)", value=0.1, step=0.01) / 100



# --- 模块 2：行情获取 ---

st.divider()

col_ticker, col_price = st.columns([1, 3])

with col_ticker:

    symbol = st.text_input("交易币种", value="BTC", placeholder="BTC, ETH...").upper()

    refresh = st.button("🔄 刷新行情", use_container_width=True)



# 获取价格

current_price = get_okx_price(symbol)

if not current_price:

    # 允许手动输入作为备用

    with col_price:

        current_price = st.number_input("无法获取行情，请手动输入价格", value=0.0)

else:

    with col_price:

        st.metric(f"{symbol}/USDT 永续现价", f"${current_price:,.2f}")



# --- 模块 3：双向推演 (核心修改) ---

if current_price > 0:

    st.markdown("### 🎯 交易计划推演")

    

    # 创建左右两列，分别对应 做多 和 做空

    col_long, col_short = st.columns(2)



    # ================= 🟢 左侧：做多逻辑 =================

    with col_long:

        st.info("🟢 **做多 (Long)** 场景")

        

        # 默认给一个合理的做多止损价 (现价下方2%)

        default_long_sl = float(current_price * 0.98)

        sl_price_long = st.number_input(

            "设定做多止损价 (Stop Loss)", 

            value=default_long_sl, 

            step=1.0, 

            format="%.2f",

            key="sl_long"

        )



        if sl_price_long >= current_price:

            st.warning("⚠️ 做多止损价必须低于现价")

        else:

            # 执行计算

            res_long = calculate_kelly_position(

                balance, win_rate, rr_ratio, friction, kelly_fraction, 

                current_price, sl_price_long, user_leverage

            )

            

            if res_long:

                st.markdown("---")

                # 结果展示

                l1, l2 = st.columns(2)

                l1.metric("建议开仓数量", f"{res_long['coin_qty']:.3f} {symbol}")

                l2.metric("仓位总价值", f"${res_long['position_value']:,.0f}")

                

                st.caption(f"需要保证金: **${res_long['required_margin']:,.2f}** (基于 {user_leverage}x)")

                

                # 风控条

                st.progress(min(res_long['sl_pct'] * 10, 1.0), text=f"止损幅度: {res_long['sl_pct']*100:.2f}%")

                

                # 风险警告

                if res_long['raw_kelly'] <= 0:

                    st.error("❌ 期望值为负，不建议开多")

                elif res_long['effective_leverage'] > 5:

                    st.error(f"⚠️ 实际杠杆过高 ({res_long['effective_leverage']:.2f}x)")



    # ================= 🔴 右侧：做空逻辑 =================

    with col_short:

        st.error("🔴 **做空 (Short)** 场景")

        

        # 默认给一个合理的做空止损价 (现价上方2%)

        default_short_sl = float(current_price * 1.02)

        sl_price_short = st.number_input(

            "设定做空止损价 (Stop Loss)", 

            value=default_short_sl, 

            step=1.0, 

            format="%.2f",

            key="sl_short"

        )



        if sl_price_short <= current_price:

            st.warning("⚠️ 做空止损价必须高于现价")

        else:

            # 执行计算

            res_short = calculate_kelly_position(

                balance, win_rate, rr_ratio, friction, kelly_fraction, 

                current_price, sl_price_short, user_leverage

            )

            

            if res_short:

                st.markdown("---")

                # 结果展示

                s1, s2 = st.columns(2)

                s1.metric("建议开仓数量", f"{res_short['coin_qty']:.3f} {symbol}")

                s2.metric("仓位总价值", f"${res_short['position_value']:,.0f}")

                

                st.caption(f"需要保证金: **${res_short['required_margin']:,.2f}** (基于 {user_leverage}x)")



                # 风控条

                st.progress(min(res_short['sl_pct'] * 10, 1.0), text=f"止损幅度: {res_short['sl_pct']*100:.2f}%")



                # 风险警告

                if res_short['raw_kelly'] <= 0:

                    st.error("❌ 期望值为负，不建议开空")

                elif res_short['effective_leverage'] > 5:

                    st.error(f"⚠️ 实际杠杆过高 ({res_short['effective_leverage']:.2f}x)")



else:

    st.info("👈 等待获取行情数据...")
