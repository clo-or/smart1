import streamlit as st
import pandas as pd
import pulp
import plotly.graph_objects as go
import plotly.express as px
import numpy as np

# Page Configuration
st.set_page_config(
    page_title="원예장비 APP 생산계획 시스템",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Look
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: #ffffff;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #e9ecef;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🚜 원예장비 제조업체 총괄생산계획 (APP) 시스템")
st.markdown("---")

# Sidebar - Parameters
with st.sidebar:
    st.header("📋 입력 파라미터")
    
    with st.expander("💰 비용 설정 (천원)", expanded=True):
        cost_material = st.number_input("재료비 (/개)", value=10)
        cost_regular = st.number_input("정규 임금 (시간당)", value=4)
        cost_overtime = st.number_input("초과 근무 수당 (시간당)", value=6)
        cost_hiring = st.number_input("신규 고용 비용 (/인)", value=300)
        cost_firing = st.number_input("해고 비용 (/인)", value=500)
        cost_holding = st.number_input("재고 유지비 (/개/월)", value=2)
        cost_backlog = st.number_input("부재고 처리비 (/개/월)", value=5)
        cost_subcontract = st.number_input("하청 총 비용 (/개)", value=30)

    with st.expander("⏳ 생산 능력 및 제약", expanded=True):
        work_days = st.number_input("월 작업 일수", value=20)
        work_hours = st.number_input("일일 작업 시간", value=8)
        max_ot_per_worker = st.number_input("인당 최대 초과시간/월", value=10)
        std_time_per_unit = st.number_input("제품당 표준 시간 (시간)", value=4)
        
    with st.expander("🏁 초기 및 기말 조건", expanded=True):
        init_workers = st.number_input("초기 인력 (명)", value=80)
        init_inventory = st.number_input("초기 재고 (개)", value=1000)
        final_inventory_min = st.number_input("기말 재고 최소치 (개)", value=500)

    st.header("⚙️ 모델 설정")
    model_type = st.radio("최적화 모델 유형", ["LP (실수)", "IP (정수)"], index=0, help="LP는 계산이 빠르지만 수치가 소수로 나올 수 있으며, IP는 현실적이지만 계산 비용이 약간 더 큽니다.")
    var_cat = 'Continuous' if "LP" in model_type else 'Integer'
    n_months = st.slider("계획 기간 (개월)", 3, 12, 6)
    
    # Default demand based on lecture notes
    default_demand = [1600, 3000, 3200, 3800, 2200, 2200]
    if len(default_demand) < n_months:
        default_demand += [2000] * (n_months - len(default_demand))
    
    demands = []
    for i in range(n_months):
        d = st.number_input(f"{i+1}월 수요", value=default_demand[i] if i < len(default_demand) else 2000)
        demands.append(d)

# Solver Function
def solve_app():
    # Define Model
    model = pulp.LpProblem("APP_Optimization", pulp.LpMinimize)
    
    # Indices
    months = range(n_months)
    
    # Decision Variables
    W = pulp.LpVariable.dicts("Workforce", months, lowBound=0, cat=var_cat)
    H = pulp.LpVariable.dicts("Hired", months, lowBound=0, cat=var_cat)
    L = pulp.LpVariable.dicts("LaidOff", months, lowBound=0, cat=var_cat)
    P = pulp.LpVariable.dicts("Production", months, lowBound=0, cat=var_cat)
    I = pulp.LpVariable.dicts("Inventory", months, lowBound=0, cat=var_cat)
    S = pulp.LpVariable.dicts("Backlog", months, lowBound=0, cat=var_cat)
    C = pulp.LpVariable.dicts("Subcontract", months, lowBound=0, cat=var_cat)
    O = pulp.LpVariable.dicts("Overtime", months, lowBound=0, cat='Continuous') 
    
    # Objective Function
    total_cost = pulp.lpSum([
        cost_regular * (work_days * work_hours) * W[t] +
        cost_overtime * O[t] +
        cost_hiring * H[t] +
        cost_firing * L[t] +
        cost_holding * I[t] +
        cost_backlog * S[t] +
        cost_subcontract * C[t] +
        cost_material * P[t]
        for t in months
    ])
    model += total_cost
    
    # Constraints
    for t in months:
        # 1. Workforce Balance
        if t == 0:
            model += W[t] == init_workers + H[t] - L[t]
        else:
            model += W[t] == W[t-1] + H[t] - L[t]
            
        # 2. Production Limit (Regular + OT)
        reg_capacity = (work_days * work_hours) / std_time_per_unit
        model += P[t] <= reg_capacity * W[t] + (O[t] / std_time_per_unit)
        
        # 3. Overtime Limit
        model += O[t] <= max_ot_per_worker * W[t]
        
        # 4. Inventory Balance
        prev_inv = init_inventory if t == 0 else I[t-1]
        prev_backlog = 0 if t == 0 else S[t-1]
        
        model += I[t] - S[t] == prev_inv - prev_backlog + P[t] + C[t] - demands[t]
        
    # 5. Final Conditions
    model += I[n_months-1] >= final_inventory_min
    model += S[n_months-1] == 0  # Final backlog should be zero
        
    # Solve
    model.solve(pulp.PULP_CBC_CMD(msg=0))
    
    if pulp.LpStatus[model.status] == 'Optimal':
        results = []
        for t in months:
            results.append({
                "월": f"{t+1}월",
                "수요": demands[t],
                "인력": W[t].varValue,
                "고용": H[t].varValue,
                "해고": L[t].varValue,
                "생산량": P[t].varValue,
                "초과시간": O[t].varValue,
                "재고": I[t].varValue,
                "부족분": S[t].varValue,
                "하청": C[t].varValue,
                "비용": (
                    cost_regular * (work_days * work_hours) * W[t].varValue +
                    cost_overtime * O[t].varValue +
                    cost_hiring * H[t].varValue +
                    cost_firing * L[t].varValue +
                    cost_holding * I[t].varValue +
                    cost_backlog * S[t].varValue +
                    cost_subcontract * C[t].varValue +
                    cost_material * P[t].varValue
                )
            })
        return pd.DataFrame(results), pulp.value(model.objective)
    else:
        return None, None

# Run Optimization
df_res, min_cost = solve_app()

if df_res is not None:
    # Key Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("총 비용", f"{min_cost:,.0f} 천원")
    m2.metric("평균 재고", f"{df_res['재고'].mean():.1f} 개")
    m3.metric("총 하청 물량", f"{df_res['하청'].sum():,.0f} 개")
    m4.metric("최종 인력", f"{df_res['인력'].iloc[-1]} 명")

    tabs = st.tabs(["📊 시각화 대시보드", "📋 상세 결과 데이터", "💰 비용 분석", "📖 이론적 배경"])

    with tabs[0]:
        col1, col2 = st.columns(2)
        
        with col1:
            fig_prod = go.Figure()
            fig_prod.add_trace(go.Bar(x=df_res['월'], y=df_res['수요'], name='수요', marker_color='#adb5bd'))
            fig_prod.add_trace(go.Scatter(x=df_res['월'], y=df_res['생산량'], name='자체생산', line=dict(color='#007bff', width=3)))
            fig_prod.add_trace(go.Scatter(x=df_res['월'], y=df_res['생산량'] + df_res['하청'], name='총 공급', line=dict(color='#28a745', width=3, dash='dot')))
            fig_prod.update_layout(title="수요 대비 생산 및 공급 현황", xaxis_title="월", yaxis_title="수량")
            st.plotly_chart(fig_prod, use_container_width=True)
            
        with col2:
            fig_inv = go.Figure()
            fig_inv.add_trace(go.Bar(x=df_res['월'], y=df_res['재고'], name='기말재고', marker_color='#17a2b8'))
            fig_inv.add_trace(go.Bar(x=df_res['월'], y=-df_res['부족분'], name='부족분(Backlog)', marker_color='#dc3545'))
            fig_inv.update_layout(title="재고 및 부족분 변동", xaxis_title="월", yaxis_title="수량", barmode='relative')
            st.plotly_chart(fig_inv, use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            fig_work = px.line(df_res, x='월', y='인력', title="월별 인력 변동", markers=True)
            fig_work.update_traces(line_color='#6610f2')
            st.plotly_chart(fig_work, use_container_width=True)
        with col4:
            fig_hf = go.Figure()
            fig_hf.add_trace(go.Bar(x=df_res['월'], y=df_res['고용'], name='신규 고용', marker_color='#28a745'))
            fig_hf.add_trace(go.Bar(x=df_res['월'], y=df_res['해고'], name='해고', marker_color='#dc3545'))
            fig_hf.update_layout(title="인력 조정 현황 (고용/해고)", xaxis_title="월", yaxis_title="인원")
            st.plotly_chart(fig_hf, use_container_width=True)

    with tabs[1]:
        st.subheader("총괄생산계획표 (Aggregate Plan Table)")
        st.dataframe(df_res.style.format({
            "수요": "{:,.0f}", "인력": "{:.1f}", "고용": "{:.1f}", "해고": "{:.1f}",
            "생산량": "{:,.0f}", "초과시간": "{:.1f}", "재고": "{:,.0f}", 
            "부족분": "{:,.0f}", "하청": "{:,.0f}", "비용": "{:,.0f}"
        }), use_container_width=True)
        
        csv = df_res.to_csv(index=False).encode('utf-8-sig')
        st.download_button("엑셀 다운로드 (CSV)", data=csv, file_name="app_result.csv", mime="text/csv")

    with tabs[2]:
        cost_elements = {
            "정규 노동비": (df_res['인력'] * (work_days * work_hours) * cost_regular).sum(),
            "초과 근무비": (df_res['초과시간'] * cost_overtime).sum(),
            "고용/해고비": (df_res['고용'] * cost_hiring + df_res['해고'] * cost_firing).sum(),
            "재고 유지비": (df_res['재고'] * cost_holding).sum(),
            "부재고 비용": (df_res['부족분'] * cost_backlog).sum(),
            "하청 비용": (df_res['하청'] * cost_subcontract).sum(),
            "재료비": (df_res['생산량'] * cost_material).sum()
        }
        cost_df = pd.DataFrame(list(cost_elements.items()), columns=['항목', '금액'])
        fig_pie = px.pie(cost_df, values='금액', names='항목', title="총 비용 구성 비율", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)
        st.table(cost_df.style.format({"금액": "{:,.0f}"}))

    with tabs[3]:
        st.header("📖 총괄생산계획(APP) 이론적 배경")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.subheader("1. 생산계획의 계층적 구조")
            st.info("""
            * **장기 계획 (RRP):** 자원소요계획. 공장 건설/확장 등 생산 능력 자체를 결정.
            * **중기 계획 (APP/MPS):** 총괄생산계획 및 주일정계획. 제품군 단위 용량 확보 및 최종 제품 주 단위 계획.
            * **단기 계획 (MRP/CRP):** 자재소요계획 및 능력소요계획. 부품 주문량/시기 결정 및 현장 실행 관리.
            """)
            st.subheader("2. 아웃소싱 및 지휘 체계")
            st.write("""
            * **아웃소싱 유형:** 외주, 협력업체, 파견, 도급, 하도급 등.
            * **지휘 명령:** 
                * **파견:** 사용사업주가 직접 지휘명령.
                * **도급/하도급:** 수탁업체가 소속 근로자를 직접 지휘.
            """)
        with col_t2:
            st.subheader("3. 모델링 접근 방식 (LP vs IP)")
            st.warning(f"""
            현재 선택된 모델: **{model_type}**
            
            * **LP (선형계획법):** 변수를 실수로 처리. 계산 속도가 빠르지만 인원수가 소수점으로 나올 수 있음.
            * **IP (정수계획법):** 변수를 정수로 제한. 실제 현장에 바로 적용 가능한 수치를 도출. 총비용이 LP보다 높을 수 있음.
            """)
            st.subheader("4. 최적화 데이터 (초기값 기준)")
            st.markdown(f"""
            * **수요 ($D_t$):** 1월~6월 (1600, 3000, 3200, 3800, 2200, 2200)
            * **표준 시간:** 개당 {std_time_per_unit}시간
            * **근무 제약:** 인당 월 {work_days * work_hours}시간 (연장 최대 {max_ot_per_worker}시간)
            * **재고 조건:** 기초 1,000 / 기말 500 이상
            """)

else:
    st.error("❌ 최적해를 찾을 수 없습니다. 제약 조건을 확인해 주세요.")

st.markdown("---")
st.caption("Developed for Gardening Equipment Manufacturer APP Production Planning")
