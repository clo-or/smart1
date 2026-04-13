import streamlit as st
import pandas as pd
import pulp
import plotly.graph_objects as go
import plotly.express as px
import numpy as np

# Page Configuration
st.set_page_config(
    page_title="스마트 제조: 생산계획 및 APP 최적화",
    page_icon="🏭",
    layout="wide"
)

# Custom CSS for Premium Design
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main {
        background-color: #fcfcfc;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #f1f3f5;
        border-radius: 8px 8px 0px 0px;
        color: #495057;
        font-weight: 600;
        padding: 10px 20px;
        transition: all 0.3s;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #ffffff;
        color: #228be6 !important;
    }
    </style>
    """, unsafe_allow_html=True)

# Title and Header
st.title("🚜 원예장비 총괄생산계획(APP) 시뮬레이터")
st.markdown("---")

tab1, tab2 = st.tabs(["⚙️ APP 모델 수립", "📊 최적화 결과 및 분석"])

with tab1:
    st.subheader("🛠️ 시나리오 설정")
    
    st.sidebar.title("🛠️ 모델 파라미터 설정")
    
    with st.sidebar.expander("📅 수요 예측 (Demand)", expanded=False):
        default_d = [2500, 4500, 5000, 5500, 4000, 4000] # 비효율 상황 유도를 위해 대폭 상향
        months_input = st.number_input("계획 기간 (개월)", 1, 12, 6)
        demands = []
        for i in range(months_input):
            val = default_d[i] if i < len(default_d) else 3000
            d = st.number_input(f"{i+1}월 수요", value=val, key=f"d_{i}")
            demands.append(d)
            
    with st.sidebar.expander("💸 비용 설정 (Cost)", expanded=True):
        c_material = st.number_input("재료비 (/개)", value=10)
        c_regular = st.number_input("정규 임금 (시간당)", value=4)
        c_overtime = st.number_input("초과 근무 수당 (시간당)", value=6)
        c_hiring = st.number_input("고용 비용 (/인)", value=1000) # 경직성 강조를 위해 상향
        c_firing = st.number_input("해고 비용 (/인)", value=1500) # 경직성 강조를 위해 상향
        c_holding = st.number_input("재고 유지비 (/개/월)", value=2)
        c_backlog = st.number_input("부재고 비용 (/개/월)", value=50) # 미납을 극도로 꺼리는 시나리오
        c_sub = st.number_input("하청 비용 (/개)", value=45) # 하청이 비싼 상황 강조

    with st.sidebar.expander("⚙️ 생산 능력 및 제약 (Capacity)", expanded=True):
        init_w = st.number_input("초기 인원 (명)", value=60) # 역량 부족 상황 유도를 위해 하향
        init_i = st.number_input("초기 재고 (개)", value=300) 
        final_i_min = st.number_input("최종 재고 최소치 (개)", value=500)
        work_days = st.number_input("작업 일수 (/월)", value=20)
        work_hours = st.number_input("정규 작업 시간 (/일)", value=8)
        ot_limit = st.number_input("초과 시간 제한 (시간/인/월)", value=10)
        std_time = st.number_input("작업 표준 시간 (시간/개)", value=4)

    model_type = st.sidebar.selectbox("🔢 변수 유형 선택", ["LP (Linear Programming)", "IP (Integer Programming)"])
    var_cat = 'Continuous' if "LP" in model_type else 'Integer'
    
    st.sidebar.markdown("<div style='margin-top: 30px; text-align: center; color: #94a3b8; font-size: 0.95em; font-weight: 600;'>C321050 이승아<br>스마트제조 프로젝트 1</div>", unsafe_allow_html=True)

    # Optimization Logic
    def run_optimization():
        prob = pulp.LpProblem("APP_Optimization", pulp.LpMinimize)
        months = range(months_input)
        
        # Decision Variables
        W = pulp.LpVariable.dicts("W", months, lowBound=0, cat=var_cat)
        H = pulp.LpVariable.dicts("H", months, lowBound=0, cat=var_cat)
        L = pulp.LpVariable.dicts("L", months, lowBound=0, cat=var_cat)
        P = pulp.LpVariable.dicts("P", months, lowBound=0, cat=var_cat)
        I = pulp.LpVariable.dicts("I", months, lowBound=0, cat=var_cat)
        S = pulp.LpVariable.dicts("S", months, lowBound=0, cat=var_cat)
        C = pulp.LpVariable.dicts("C", months, lowBound=0, cat=var_cat)
        O = pulp.LpVariable.dicts("O", months, lowBound=0, cat='Continuous') # OT is usually continuous

        # Objective: Z = 640W + 6O + 300H + 500L + 2I + 5S + 10P + 30C
        # Monthly base wage = c_regular * work_days * work_hours = 4 * 20 * 8 = 640
        reg_wage_monthly = c_regular * work_days * work_hours
        
        prob += pulp.lpSum([
            reg_wage_monthly * W[t] + c_overtime * O[t] + c_hiring * H[t] + 
            c_firing * L[t] + c_holding * I[t] + c_backlog * S[t] + 
            c_material * P[t] + c_sub * C[t] 
            for t in months
        ])

        # Constraints
        for t in months:
            # 1. Workforce balance
            if t == 0:
                prob += W[t] == init_w + H[t] - L[t]
            else:
                prob += W[t] == W[t-1] + H[t] - L[t]
            
            # 2. Production capacity: P_t <= (W_t * 8 * 20 / 4) + (O_t / 4)
            # 8*20/4 = 160/4 = 40. So P_t <= 40W_t + 0.25*O_t
            reg_cap_per_worker = (work_hours * work_days) / std_time
            prob += P[t] <= reg_cap_per_worker * W[t] + (O[t] / std_time)
            
            # 3. Inventory balance
            prev_i = init_i if t == 0 else I[t-1]
            prev_s = 0 if t == 0 else S[t-1]
            prob += I[t] - S[t] == prev_i - prev_s + P[t] + C[t] - demands[t]
            
            # 4. Overtime limit
            prob += O[t] <= ot_limit * W[t]

        # 5. Final conditions
        prob += I[months_input-1] >= final_i_min
        prob += S[months_input-1] == 0
        
        status = prob.solve(pulp.PULP_CBC_CMD(msg=0))
        
        if pulp.LpStatus[status] == 'Optimal':
            res = []
            for t in months:
                res.append({
                    "Month": t+1,
                    "Demand": demands[t],
                    "Workers(W)": W[t].varValue,
                    "Hired(H)": H[t].varValue,
                    "LaidOff(L)": L[t].varValue,
                    "Prod(P)": P[t].varValue,
                    "Inv(I)": I[t].varValue,
                    "Shortage(S)": S[t].varValue,
                    "Sub(C)": C[t].varValue,
                    "OT(O)": O[t].varValue
                })
            return pd.DataFrame(res), pulp.value(prob.objective)
        else:
            return None, None

    if st.button("🚀 최적화 실행", use_container_width=True):
        # Store previous result before running new optimization
        if 'df_res' in st.session_state:
            st.session_state['prev_df_res'] = st.session_state['df_res']
            st.session_state['prev_total_cost'] = st.session_state['total_cost']
            st.session_state['prev_metrics'] = st.session_state.get('curr_metrics', None)

        df_res, total_cost = run_optimization()
        if df_res is not None:
            st.session_state['df_res'] = df_res
            st.session_state['total_cost'] = total_cost
            st.success("✅ 최적해 도출 완료! '최적화 결과 및 분석' 탭에서 확인하세요.")
        else:
            st.error("❌ 최적해를 찾을 수 없습니다. 제약조건을 완화해 보세요.")

with tab2:
    if 'df_res' in st.session_state:
        df = st.session_state['df_res']
        cost = st.session_state['total_cost']
        
        # Summary & Insights Section
        # Calculate current metrics
        total_demand = df['Demand'].sum()
        total_prod = df['Prod(P)'].sum()
        total_sub = df['Sub(C)'].sum()
        total_backlog = df['Shortage(S)'].sum()
        
        avg_utilization = (total_prod * std_time) / (df['Workers(W)'].sum() * work_days * work_hours) * 100
        sub_ratio = (total_sub / (total_prod + total_sub)) * 100 if (total_prod + total_sub) > 0 else 0
        service_level = (1 - total_backlog / total_demand) * 100 if total_demand > 0 else 100
        cost_per_unit = cost / total_demand if total_demand > 0 else 0
        
        curr_metrics = {
            "cost": cost,
            "util": avg_utilization,
            "sub": sub_ratio,
            "service": service_level,
            "unit_cost": cost_per_unit
        }
        st.session_state['curr_metrics'] = curr_metrics

        # Comparison Logic
        st.markdown("### 📈 핵심 성과 지표 (Operational Metrics)")
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        
        def get_delta(key, current_val, inverse=False):
            if 'prev_metrics' in st.session_state and st.session_state.get('prev_metrics'):
                prev_val = st.session_state['prev_metrics'].get(key, None)
                if prev_val is not None and prev_val != 0:
                    diff = current_val - prev_val
                    pct = (diff / prev_val) * 100
                    # 비용은 늘어나면 빨간색(inverse), 효율은 늘어나면 초록색(normal)
                    color = "inverse" if inverse else "normal"
                    return f"{pct:+.1f}%", color
            return None, "normal"

        # 내부 로직용 판별 (고용/해고 비용이 높으면 경직된 것으로 간주)
        is_rigid = c_hiring > 800 or c_firing > 800
        internal_cost = c_material + (c_regular * std_time) 
        
        # 1. 총 비용
        cost_delta, cost_color = get_delta("cost", cost, inverse=True)
        col_m1.metric("총 비용 (Total Cost)", f"{cost/1000:,.1f}M", delta=cost_delta, delta_color=cost_color)
        
        # 2. 평균 가동률
        util_delta, util_delta_color = get_delta("util", avg_utilization)
        col_m2.metric("평균 가동률", f"{avg_utilization:.1f}%", delta=util_delta, delta_color=util_delta_color)
        
        # 3. 하청 의존도
        sub_delta, sub_delta_color = get_delta("sub", sub_ratio, inverse=True)
        col_m3.metric("하청 의존도", f"{sub_ratio:.1f}%", delta=sub_delta, delta_color=sub_delta_color)
        
        # 4. 납기 준수율
        srv_delta, srv_delta_color = get_delta("service", service_level)
        col_m4.metric("납기 준수율", f"{service_level:.1f}%", delta=srv_delta, delta_color=srv_delta_color)

        # Charts
        st.markdown("---")
        c1, c2 = st.columns(2)
        
        with c1:
            fig_prod = go.Figure()
            fig_prod.add_trace(go.Bar(x=df['Month'], y=df['Demand'], name='수요 (Demand)', marker_color='#adb5bd', opacity=0.4))
            fig_prod.add_trace(go.Bar(x=df['Month'], y=df['Prod(P)'], name='자체생산 (Internal)', marker_color='#228be6'))
            fig_prod.add_trace(go.Bar(x=df['Month'], y=df['Sub(C)'], name='하청 (Subcontract)', marker_color='#fab005'))
            fig_prod.update_layout(title="<b>수요 대비 공급 구성 (자체 vs 하청)</b>", barmode='stack', xaxis_title="월", yaxis_title="수량", template="plotly_white")
            st.plotly_chart(fig_prod, use_container_width=True)
            
            fig_work = go.Figure()
            fig_work.add_trace(go.Scatter(x=df['Month'], y=df['Workers(W)'], mode='lines+markers', name='인력', line=dict(color='#7950f2', width=3)))
            fig_work.update_layout(title="<b>월별 인력 변동 추이</b>", xaxis_title="월", yaxis_title="인원", template="plotly_white")
            st.plotly_chart(fig_work, use_container_width=True)

        with c2:
            fig_inv = go.Figure()
            fig_inv.add_trace(go.Bar(x=df['Month'], y=df['Inv(I)'], name='재고', marker_color='#15aabf'))
            fig_inv.add_trace(go.Bar(x=df['Month'], y=-df['Shortage(S)'], name='부족분', marker_color='#fa5252'))
            fig_inv.update_layout(title="<b>재고 및 부족분 현황</b>", xaxis_title="월", yaxis_title="수량", barmode='relative', template="plotly_white")
            st.plotly_chart(fig_inv, use_container_width=True)
            
            # Sub-cost breakdown
            cost_items = {
                "정규 노동": (df['Workers(W)'] * c_regular * work_days * work_hours).sum(),
                "연장 근로": (df['OT(O)'] * c_overtime).sum(),
                "고용/해고": (df['Hired(H)'] * c_hiring + df['LaidOff(L)'] * c_firing).sum(),
                "재고 유지": (df['Inv(I)'] * c_holding).sum(),
                "부족분(Backlog)": (df['Shortage(S)'] * c_backlog).sum(),
                "재료비": (df['Prod(P)'] * c_material).sum(),
                "하청": (df['Sub(C)'] * c_sub).sum()
            }
            cost_df = pd.DataFrame(list(cost_items.items()), columns=['Item', 'Amount'])
            fig_pie = px.pie(cost_df, values='Amount', names='Item', title="<b>총 비용 구성 비율</b>", color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("📋 상세 최적화 결과 테이블")
        st.dataframe(df.style.format({
            "Workers(W)": "{:.1f}", "Hired(H)": "{:.1f}", "LaidOff(L)": "{:.1f}",
            "Prod(P)": "{:,.0f}", "Inv(I)": "{:,.0f}", "Shortage(S)": "{:,.0f}",
            "Sub(C)": "{:,.0f}", "OT(O)": "{:.1f}"
        }), use_container_width=True)
        
    else:
        st.warning("⚠️ 아직 최적화를 실행하지 않았습니다. 'APP 모델 수립' 탭에서 실행 버튼을 눌러주세요.")

st.markdown("---")
st.markdown("<div style='margin-top: 30px; text-align: center; color: #94a3b8; font-size: 0.95em; font-weight: 600;'>C321050 이승아<br>스마트제조 프로젝트 1</div>", unsafe_allow_html=True)
