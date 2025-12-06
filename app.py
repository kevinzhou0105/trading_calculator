import streamlit as st

import requests



# --- 页面全局配置 ---

st.set_page_config(

    page_title="动态仓位计算器",

    page_icon="⚖️",

    layout="wide"

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



# --- 核心函数 1: 计算凯利风险预算 (Risk Budget) ---

def calculate_kelly_budget(balance, win_rate, rr_ratio, friction, kelly_fraction):

    # 修正盈亏比

    real_rr = (rr_ratio - friction) / (1 + friction)

    

    if real_rr <= 0:

        return 0, 0, 0 # 期望值为负

    

    # 凯利公式

    raw_kelly = (real_rr * win_rate - (1 - win_rate)) / real_rr

    

    # 应用凯利分数

    risk_per_trade_pct = max(0, raw_kelly * kelly_fraction)

    risk_amount = balance * risk_per_trade_pct

    

    return raw_kelly, risk_per_trade_pct, risk_amount



# --- 核心函数 2: 计算具体仓位 (Position Sizing) ---

def calculate_position_details(entry_price, sl_price, risk_amount, leverage_input, balance):

    # 1. 计算止损幅度

    if sl_price < entry_price:

        direction = "long"

        sl_pct = (entry_price - sl_price) / entry_price

    else:

        direction = "short"

        sl_pct = (sl_price - entry_price) / entry_price

        

    if sl_pct < 0.001: return None # 保护机制



    # 2. 核心公式：名义价值 = 风险金额 / 止损幅度

    position_value = risk_amount / sl_pct 

    

    # 3. 币数量

    coin_qty = position_value / entry_price

    

    # 4. 保证金

    required_margin = position_value / leverage_input

    

    # 5. 实际有效杠杆

    effective_leverage = position_value / balance

    

    return {

        "direction": direction,

        "sl_pct": sl_pct,

        "position_value": position_value,

        "coin_qty": coin_qty,

        "required_margin": required_margin,

        "effective_leverage": effective_leverage

    }



# ================= UI 布局 =================



st.title("⚖️ 动态仓位计算器")

st.markdown("Connected to **OKX V5 API** (USDT-SWAP)")



# --- 模块 1：账户与风控 ---

with st.container(border=True):

    st.subheader("🛠️ 账户与风控参数")

    

    c1, c2, c3 = st.columns(3)

    with c1:

        balance = st.number_input("账户可用余额 (USDT)", value=10000.0, step=100.0)

    with c2:

        user_leverage = st.number_input("开单杠杆倍数 (Leverage)", 0.1, 20.0, 5.0, 0.1, format="%.2f")

    with c3:

        kelly_fraction = st.select_slider(

            "凯利激进程度", options=[0.1, 0.2, 0.25, 0.5, 1.0], value=0.25,

            format_func=lambda x: f"1/{int(1/x)} Kelly" if x < 1 else "Full Kelly"

        )



    c4, c5, c6 = st.columns(3)

    with c4: win_rate = st.number_input("策略胜率 (%)", value=51.0, step=0.5) / 100

    with c5: rr_ratio = st.number_input("目标盈亏比 (R:R)", value=1.5, step=0.1)

    with c6: friction = st.number_input("预估磨损 (手续费+滑点 %)", value=0.1, step=0.01) / 100



# --- 模块 2：建议下注额度 (新增请求：前置展示) ---

raw_kelly, risk_pct, risk_amount = calculate_kelly_budget(balance, win_rate, rr_ratio, friction, kelly_fraction)



st.markdown("### 💰 建议下注额度 (Risk Budget)")

if raw_kelly <= 0:

    st.error(f"❌ 当前策略期望值为负 (Win: {win_rate:.0%}, RR: {rr_ratio})，凯利公式建议空仓！")

else:

    # 使用 info 框体展示核心计算结果

    with st.info(f"💡 基于凯利公式，本笔交易建议风险敞口为 **{risk_pct*100:.2f}%**"):

        k1, k2, k3 = st.columns(3)

        k1.metric("1. 理论凯利值 (Full)", f"{raw_kelly*100:.2f}%")

        k2.metric(f"2. 实际采用值 ({kelly_fraction}x)", f"{risk_pct*100:.2f}%")

        k3.metric("3. 亏损上限 (Risk Amount)", f"${risk_amount:,.2f}", help="如果触发止损，你将损失的本金金额")

    

    st.caption(f"👉 **这意味着：** 无论你如何开仓，你的止损单触发时，亏损金额不应超过 **${risk_amount:,.2f}** (即你只能接受亏这么多钱)。")



# --- 模块 3：行情获取 ---

st.divider()

col_ticker, col_price = st.columns([1, 3])

with col_ticker:

    symbol = st.text_input("交易币种", value="BTC").upper()

    refresh = st.button("🔄 刷新行情", use_container_width=True)



current_price = get_okx_price(symbol)

if not current_price:

    with col_price: current_price = st.number_input("无法获取行情，请手动输入价格", value=0.0)

else:

    with col_price: st.metric(f"{symbol}/USDT 永续现价", f"${current_price:,.2f}")



# --- 模块 4：交易计划推演 ---

if current_price > 0 and raw_kelly > 0:

    st.markdown("### 🎯 交易计划推演")

    

    col_long, col_short = st.columns(2)



    # === 通用渲染函数，避免重复写两遍代码 ===

    def render_scenario(col, direction, default_sl):

        with col:

            is_long = direction == "long"

            header_color = "🟢" if is_long else "🔴"

            label = "做多 (Long)" if is_long else "做空 (Short)"

            st.subheader(f"{header_color} {label}")

            

            # 1. 输入止损价

            sl_input = st.number_input(

                f"设定{label}止损价", 

                value=float(default_sl), format="%.2f", step=1.0, key=f"sl_{direction}"

            )

            

            # 2. 立即计算并展示止损幅度 (优化点1：进度条紧跟输入框)

            if is_long:

                sl_pct_preview = (current_price - sl_input) / current_price

                valid = sl_input < current_price

            else:

                sl_pct_preview = (sl_input - current_price) / current_price

                valid = sl_input > current_price



            if valid and sl_pct_preview > 0:

                # 进度条展示止损宽度 (上限设为10%防止溢出)

                st.progress(min(sl_pct_preview * 10, 1.0), text=f"止损幅度: {sl_pct_preview*100:.2f}%")

                

                # 3. 计算仓位详情

                res = calculate_position_details(current_price, sl_input, risk_amount, user_leverage, balance)

                

                if res:

                    st.markdown("---")

                    r1, r2 = st.columns(2)

                    r1.metric("建议开仓数量", f"{res['coin_qty']:.3f} {symbol}")

                    r2.metric("名义仓位价值", f"${res['position_value']:,.0f}")

                    st.caption(f"保证金占用: **${res['required_margin']:,.2f}**")

                    

                    # 4. 风险警告与公式拆解 (优化点3：展示计算过程)

                    eff_lev = res['effective_leverage']

                    if eff_lev > 5:

                        msg = f"⚠️ 实际杠杆过高 ({eff_lev:.2f}x)"

                        if eff_lev > 10:

                            st.error(msg)

                        else:

                            st.warning(msg)

                        

                        # 展示计算过程

                        with st.expander("🧐 为什么仓位这么大？ (点击查看计算过程)"):

                            st.markdown(f"""

                            **为了让您在止损 {res['sl_pct']*100:.2f}% 时刚好亏损 ${risk_amount:,.0f} (您的风险预算)，系统进行了如下计算：**

                            

                            1. **名义价值计算**:

                            $$

                            \\text{{仓位价值}} = \\frac{{\\text{{风险金额}}}}{{\\text{{止损幅度}}}} = \\frac{{{risk_amount:.0f}}}{{{res['sl_pct']:.4f}}} \\approx {res['position_value']:,.0f} \\text{{ U}}

                            $$

                            

                            2. **实际杠杆计算**:

                            $$

                            \\text{{实际杠杆}} = \\frac{{\\text{{仓位价值}}}}{{\\text{{账户余额}}}} = \\frac{{{res['position_value']:,.0f}}}{{{balance}}} \\approx {eff_lev:.2f} \\text{{ x}}

                            $$

                            

                            *建议：放宽止损距离或降低凯利系数，可降低杠杆倍数。*

                            """)

            else:

                if not valid:

                    st.warning("⚠️ 止损价格设置方向错误")



    # 执行渲染

    render_scenario(col_long, "long", current_price * 0.98)

    render_scenario(col_short, "short", current_price * 1.02)



elif raw_kelly <= 0:

    st.warning("👈 请先调整参数，确保策略期望值为正。")

else:

    st.info("👈 等待获取行情数据...")
