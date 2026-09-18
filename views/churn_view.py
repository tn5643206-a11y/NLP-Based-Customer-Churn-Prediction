import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import text
import joblib
import os
from myapp import app, db

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "myapp", "churn_model.pkl")


@st.cache_resource
def load_churn_model():
    if os.path.exists(MODEL_PATH):
        try:
            return joblib.load(MODEL_PATH)
        except Exception as e:
            st.warning(f"Không thể load churn_model.pkl: {e}")
    return None


def fetch_customer_predictions(search_kw="", risk_filter="Tất cả"):
    conditions = ["1=1"]
    params = {}

    if search_kw.strip():
        conditions.append("(c.customer_code LIKE :kw OR c.name LIKE :kw)")
        params["kw"] = f"%{search_kw.strip()}%"

    if risk_filter != "Tất cả":
        conditions.append("p.risk_level LIKE :risk")
        params["risk"] = f"%{risk_filter}%"

    where_clause = " AND ".join(conditions)

    query = text(f"""
        WITH LatestPredictions AS (
            SELECT customer_id, churn_risk_percent, risk_level, last_analyzed,
                   ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY last_analyzed DESC) as rn
            FROM predictions
        )
        SELECT 
            c.id AS customer_id,
            c.customer_code,
            c.name AS customer_name,
            ROUND(p.churn_risk_percent, 2) AS churn_risk_percent,
            p.risk_level,
            p.last_analyzed,
            (SELECT COUNT(*) FROM reviews r WHERE r.customer_id = c.id) AS total_reviews,
            (SELECT AVG(CAST(rating_stars AS FLOAT)) FROM reviews r WHERE r.customer_id = c.id) AS avg_stars
        FROM LatestPredictions p
        JOIN customers c ON p.customer_id = c.id
        WHERE p.rn = 1 AND {where_clause}
        ORDER BY p.churn_risk_percent DESC
    """)

    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn, params=params)


def fetch_customer_prediction_history(customer_id):
    query = text("""
        SELECT 
            p.last_analyzed AS prediction_date,
            ROUND(p.churn_risk_percent, 2) AS churn_risk_percent,
            p.risk_level
        FROM predictions p
        WHERE p.customer_id = :customer_id
        ORDER BY p.last_analyzed ASC
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn, params={"customer_id": customer_id})


def simulate_churn_probability(model_bundle, features: dict):
    feature_order = [
        "total_reviews",
        "avg_product_price",
        "avg_comment_length",
        "complaint_quality_cnt",
        "complaint_shipping_cnt",
        "complaint_packaging_cnt",
        "complaint_taste_cnt"
    ]

    # Đảm bảo có giá trị mặc định cho độ dài comment nếu chưa nhập trên UI
    if "avg_comment_length" not in features:
        features["avg_comment_length"] = 15.0

    if model_bundle is not None:
        try:
            input_df = pd.DataFrame([[features[col] for col in feature_order]], columns=feature_order)
            if hasattr(model_bundle, "predict_proba"):
                prob = model_bundle.predict_proba(input_df)[0][1] * 100
                return round(float(prob), 2)
            elif isinstance(model_bundle, dict) and "model" in model_bundle:
                clf = model_bundle["model"]
                scaler = model_bundle.get("scaler")
                X = scaler.transform(input_df) if scaler else input_df
                prob = clf.predict_proba(X)[0][1] * 100
                return round(float(prob), 2)
        except Exception:
            pass

    reviews = features.get("total_reviews", 2)
    complaints = (
        features.get("complaint_quality_cnt", 0) +
        features.get("complaint_shipping_cnt", 0) +
        features.get("complaint_packaging_cnt", 0) +
        features.get("complaint_taste_cnt", 0)
    )
    price = features.get("avg_product_price", 250000)

    z = -0.3 * (reviews - 2) + 0.7 * complaints - 0.000001 * (price - 250000)
    prob = 1 / (1 + np.exp(-np.clip(z, -4, 4)))
    return round(float(prob * 100), 2)

def render():
    st.markdown("""
        <div style="margin-bottom: 20px;">
            <h2 style="color:#004D6B; font-weight:800; margin-bottom:4px;">
                Dự Báo Khách Hàng Rời Bỏ
            </h2>
            <p style="color:#64748B; font-size:14px; margin:0;">
                Mô hình Machine Learning phân tích độ nhạy của hành vi khách hàng và cảnh báo nguy cơ Churn.
            </p>
        </div>
    """, unsafe_allow_html=True)

    tab_overview, tab_simulate = st.tabs(["Danh Sách Dự Báo Khách Hàng", "Giả Lập Tham Số"])

    with tab_overview:
        c_filter1, c_filter2 = st.columns([2, 1])
        with c_filter1:
            kw = st.text_input("Tìm theo tên hoặc mã khách hàng:", placeholder="Nhập tên hoặc mã...")
        with c_filter2:
            risk_choice = st.selectbox("Lọc mức rủi ro:", ["Tất cả", "High", "Medium", "Low"])

        df_cust = fetch_customer_predictions(search_kw=kw, risk_filter=risk_choice)

        if not df_cust.empty:
            st.caption(f"Tìm thấy **{len(df_cust):,}** khách hàng thỏa mãn điều kiện")

            df_display = df_cust.copy()
            df_display["avg_stars"] = df_display["avg_stars"].apply(lambda v: f"{v:.1f}" if pd.notna(v) else "—")
            df_display["churn_risk_percent"] = df_display["churn_risk_percent"].apply(lambda v: f"{v:.1f}%")

            st.dataframe(
                df_display[[
                    "customer_code", "customer_name", "churn_risk_percent",
                    "risk_level", "total_reviews", "avg_stars", "last_analyzed"
                ]].rename(columns={
                    "customer_code": "Mã Khách",
                    "customer_name": "Tên Khách Hàng",
                    "churn_risk_percent": "Xác Suất Rời Bỏ",
                    "risk_level": "Mức Rủi Ro",
                    "total_reviews": "Số Review",
                    "avg_stars": "Đánh Giá TB",
                    "last_analyzed": "Phân Tích Gần Nhất"
                }),
                use_container_width=True,
                height=420
            )
        else:
            st.info("Không tìm thấy dữ liệu khách hàng phù hợp.")

    with tab_simulate:
        st.markdown(
            "<p style='color:#334155; font-size:14px;'>Điều chỉnh các tham số hành vi bên dưới để quan sát phản ứng của mô hình Random Forest:</p>",
            unsafe_allow_html=True)
        st.write("")

        col_input, col_result = st.columns([5, 4], gap="large")

        with col_input:
            st.markdown(
                "<h4 style='color:#004D6B; font-size:15px; font-weight:700;'>1. Tần Suất Mua Sắm & Giá Trị Đơn</h4>",
                unsafe_allow_html=True)

            c_rfm1, c_rfm2 = st.columns(2)
            with c_rfm1:
                total_reviews = st.number_input("Tổng số lượt đánh giá:", min_value=1, max_value=50, value=2, step=1)
            with c_rfm2:
                avg_price = st.number_input("Giá trị TB sản phẩm (VND):", min_value=10000, max_value=5000000, value=250000, step=20000)

            avg_len = st.slider(
                "Độ dài bình luận trung bình (số từ):",
                min_value=1, max_value=100, value=15, step=1,
                help="Người phàn nàn bức xúc thường viết câu chữ dài hơn"
            )

            st.write("")
            st.markdown(
                "<h4 style='color:#004D6B; font-size:15px; font-weight:700;'>2. Phân Cụm Khiếu Nại NLP (Số lần phát sinh)</h4>",
                unsafe_allow_html=True)

            c_comp1, c_comp2 = st.columns(2)
            with c_comp1:
                comp_quality = st.number_input("Lỗi chất lượng hạt (Cụm 1):", min_value=0, max_value=10, value=0, step=1)
                comp_packaging = st.number_input("Lỗi bao bì/định lượng (Cụm 3):", min_value=0, max_value=10, value=0, step=1)
            with c_comp2:
                comp_shipping = st.number_input("Sự cố vận chuyển (Cụm 0):", min_value=0, max_value=10, value=0, step=1)
                comp_taste = st.number_input("Lỗi cảm quan hương vị (Cụm 2):", min_value=0, max_value=10, value=0, step=1)

        model_bundle = load_churn_model()

        simulated_prob = simulate_churn_probability(
            model_bundle,
            {
                "total_reviews": total_reviews,
                "avg_product_price": avg_price,
                "avg_comment_length": avg_len,
                "complaint_quality_cnt": comp_quality,
                "complaint_shipping_cnt": comp_shipping,
                "complaint_packaging_cnt": comp_packaging,
                "complaint_taste_cnt": comp_taste
            }
        )

        if simulated_prob >= 70.0:
            risk_badge = "High Risk"
            badge_color = "#E05252"
            status_desc = "Khách hàng có nguy cơ rất cao sẽ rời bỏ gian hàng. Cần kích hoạt voucher cứu vãn hoặc bộ phận CSKH liên hệ xử lý ngay."
        elif simulated_prob >= 40.0:
            risk_badge = "Medium Risk"
            badge_color = "#F59E0B"
            status_desc = "Khách hàng đang có dấu hiệu giảm gắn bó. Cần gửi email chăm sóc hoặc ưu đãi cá nhân hóa."
        else:
            risk_badge = "Low Risk"
            badge_color = "#10B981"
            status_desc = "Khách hàng duy trì tương tác tốt và hài lòng. Tiếp tục giữ vững trải nghiệm dịch vụ."

        with col_result:
            st.markdown(
                "<h4 style='color:#004D6B; font-size:15px; font-weight:700; text-align:center;'>Dự Báo Rủi Ro (Random Forest)</h4>",
                unsafe_allow_html=True)

            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=simulated_prob,
                number={'suffix': "%", 'font': {'size': 36, 'color': '#0F172A'}},
                gauge={
                    'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': "#CBD5E1"},
                    'bar': {'color': badge_color, 'thickness': 0.28},
                    'bgcolor': "#FFFFFF",
                    'borderwidth': 1,
                    'bordercolor': "#E2E8F0",
                    'steps': [
                        {'range': [0, 40], 'color': 'rgba(16, 185, 129, 0.12)'},
                        {'range': [40, 70], 'color': 'rgba(245, 158, 11, 0.12)'},
                        {'range': [70, 100], 'color': 'rgba(224, 82, 82, 0.12)'}
                    ]
                }
            ))
            fig_gauge.update_layout(
                height=240,
                margin=dict(t=15, b=10, l=25, r=25),
                paper_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

            st.markdown(f"""
                <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid {badge_color}; border-radius:12px; padding:16px; box-shadow:0 3px 8px rgba(0,0,0,0.03); text-align:center;">
                    <span style="font-size:12px; font-weight:700; color:#64748B; text-transform:uppercase;">Phân Nhóm Nguy Cơ:</span>
                    <h3 style="color:{badge_color}; margin:6px 0; font-size:22px; font-weight:800;">{risk_badge}</h3>
                    <p style="font-size:13px; color:#475569; margin:8px 0 0 0; line-height:1.4;">
                        {status_desc}
                    </p>
                </div>
            """, unsafe_allow_html=True)

    st.write("")
    st.markdown("---")

    st.markdown("""
        <h3 style='color:#004D6B; font-size:18px; font-weight:700;'>
            Biểu Đồ Biến Động Rủi Ro Rời Bỏ Theo Thời Gian
        </h3>
    """, unsafe_allow_html=True)

    customer_options = {
        row["customer_id"]: f"#{row['customer_id']} - {row['customer_name']}"
        for _, row in df_cust.iterrows()
    }

    selected_cust_id = st.selectbox(
        "Chọn khách hàng để xem lịch sử dự báo qua các đợt phân tích:",
        options=list(customer_options.keys()),
        format_func=lambda x: customer_options[x]
    )

    if selected_cust_id:
        df_history = fetch_customer_prediction_history(selected_cust_id)

        if df_history.empty:
            st.info("Khách hàng này chưa có dữ liệu dự báo trong cơ sở dữ liệu.")
        elif len(df_history) == 1:
            last_date = df_history.iloc[0]["prediction_date"]
            risk_val = df_history.iloc[0]["churn_risk_percent"]
            st.info(
                f"Khách hàng {customer_options[selected_cust_id]} mới có 1 mốc phân tích vào ngày {last_date} (Rủi ro: {risk_val}%). Cần thêm dữ liệu các đợt phân tích tiếp theo để vẽ đường xu hướng.")
        else:
            fig_trend = px.line(
                df_history,
                x="prediction_date",
                y="churn_risk_percent",
                markers=True,
                labels={
                    "prediction_date": "Thời Điểm Phân Tích",
                    "churn_risk_percent": "Xác Suất Rời Bỏ (%)"
                },
                title=f"Xu hướng rủi ro của {customer_options[selected_cust_id]}"
            )
            fig_trend.update_traces(
                line_color="#0081B3",
                line_width=3,
                marker=dict(size=8, color="#004D6B")
            )
            fig_trend.update_layout(
                yaxis=dict(range=[0, 100], ticksuffix="%"),
                plot_bgcolor="#FFFFFF",
                paper_bgcolor="#FFFFFF",
                height=300,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_trend, use_container_width=True)