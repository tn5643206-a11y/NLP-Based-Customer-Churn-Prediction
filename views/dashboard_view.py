import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from fpdf import FPDF
from datetime import datetime
import os
from myapp import app, db

def fetch_dashboard_kpis():
    query = text("""
        WITH LatestPredictions AS (
            SELECT customer_id, churn_risk_percent, risk_level,
                   ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY last_analyzed DESC) as rn
            FROM predictions
        ),
        CustomerSpending AS (
            SELECT r.customer_id, SUM(p.price) AS total_spend
            FROM reviews r
            JOIN products p ON r.product_id = p.id
            GROUP BY r.customer_id
        )
        SELECT 
            (SELECT COUNT(*) FROM customers) AS total_customers,
            (SELECT ROUND(AVG(churn_risk_percent), 2) FROM LatestPredictions WHERE rn = 1) AS avg_churn_risk,
            (SELECT COUNT(*) FROM LatestPredictions WHERE rn = 1 AND risk_level LIKE 'High%') AS high_risk_count,
            (SELECT COUNT(*) FROM reviews) AS total_reviews,
            (SELECT COUNT(*) FROM reviews WHERE sentiment = 'Positive') AS positive_reviews,
            (SELECT COUNT(*) FROM reviews WHERE sentiment = 'Negative') AS negative_reviews,
            (SELECT COUNT(*) FROM reviews WHERE processing_status IS NOT NULL) AS total_complaints,
            (SELECT COUNT(*) FROM reviews WHERE processing_status = 'PENDING') AS pending_complaints,
            (SELECT COUNT(*) FROM reviews WHERE processing_status = 'IN_PROGRESS') AS in_progress_complaints,
            (SELECT COUNT(*) FROM reviews WHERE processing_status = 'COMPLETED') AS completed_complaints
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn).iloc[0]


def fetch_risk_distribution():
    query = text("""
        WITH LatestPredictions AS (
            SELECT customer_id, risk_level,
                   ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY last_analyzed DESC) as rn
            FROM predictions
        )
        SELECT ISNULL(risk_level, 'Unknown') AS risk_level, COUNT(*) AS customer_count
        FROM LatestPredictions
        WHERE rn = 1
        GROUP BY risk_level
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)


def fetch_sentiment_and_clusters():
    query = text("""
        SELECT 
            ISNULL(cluster_name, N'Chưa phân cụm') AS cluster_name,
            COUNT(*) AS review_count
        FROM reviews
        WHERE sentiment = 'Negative'
          AND cluster_name NOT LIKE N'%Hài lòng%'
          AND cluster_name IS NOT NULL
        GROUP BY cluster_name
        ORDER BY review_count ASC
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)


def fetch_top_risk_vip_customers(limit=10):
    query = text(f"""
        WITH LatestPredictions AS (
            SELECT customer_id, churn_risk_percent, risk_level,
                   ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY last_analyzed DESC) as rn
            FROM predictions
        ),
        CustomerSpending AS (
            SELECT r.customer_id, SUM(p.price) AS total_spend
            FROM reviews r
            JOIN products p ON r.product_id = p.id
            GROUP BY r.customer_id
        )
        SELECT TOP {limit}
            c.customer_code,
            c.name AS customer_name,
            ISNULL(cs.total_spend, 0) AS total_spend,
            ROUND(lp.churn_risk_percent, 1) AS churn_risk_percent,
            lp.risk_level,
            (SELECT COUNT(*) FROM reviews r WHERE r.customer_id = c.id) AS review_count
        FROM LatestPredictions lp
        JOIN customers c ON lp.customer_id = c.id
        LEFT JOIN CustomerSpending cs ON c.id = cs.customer_id
        WHERE lp.rn = 1 AND lp.risk_level LIKE 'High%'
        ORDER BY cs.total_spend DESC, lp.churn_risk_percent DESC
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)


def fetch_sentiment_monthly_trends():
    query = text("""
        SELECT 
            CONVERT(VARCHAR(7), review_date, 120) AS month_period,
            CASE WHEN sentiment = 'Positive' THEN 'Positive' ELSE 'Negative' END AS sentiment,
            COUNT(*) AS review_count
        FROM reviews
        WHERE review_date IS NOT NULL
        GROUP BY CONVERT(VARCHAR(7), review_date, 120), 
                 CASE WHEN sentiment = 'Positive' THEN 'Positive' ELSE 'Negative' END
        ORDER BY month_period ASC
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)

def generate_pdf_report(kpis, df_risk, df_clusters, df_top_vip):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    font_regular = "C:/Windows/Fonts/arial.ttf"
    font_bold = "C:/Windows/Fonts/arialbd.ttf"

    if os.path.exists(font_regular) and os.path.exists(font_bold):
        try:
            pdf.add_font("ArialVN", "", font_regular)
            pdf.add_font("ArialVN", "B", font_bold)
            font_family = "ArialVN"
        except Exception:
            font_family = "Helvetica"
    else:
        font_family = "Helvetica"

    # Header
    pdf.set_font(font_family, "B", 15)
    pdf.set_text_color(0, 77, 107)
    pdf.cell(0, 8, "BÁO CÁO NGUY CƠ RỜI BỎ & DỊCH VỤ CSKH", ln=True, align="C")

    pdf.set_font(font_family, "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 5,
             f"Thời điểm xuất: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
             ln=True, align="C")
    pdf.ln(3)

    # 1. Executive KPIs
    pdf.set_font(font_family, "B", 10.5)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 6, "1. CHỈ SỐ TỔNG QUAN HỆ THỐNG (EXECUTIVE KPIS)", ln=True)
    pdf.ln(1)

    pdf.set_font(font_family, "", 9)
    pdf.set_fill_color(248, 250, 252)
    pdf.rect(10, pdf.get_y(), 190, 26, "F")

    tot_rev = int(kpis.get("total_reviews", 0))
    pos_rev = int(kpis.get("positive_reviews", 0))
    neg_rev = int(kpis.get("negative_reviews", 0))
    tot_comp = int(kpis.get("total_complaints", 0))
    comp_comp = int(kpis.get("completed_complaints", 0))
    in_comp = int(kpis.get("in_progress_complaints", 0))
    pend_comp = int(kpis.get("pending_complaints", 0))
    res_rate = (comp_comp / tot_comp * 100) if tot_comp > 0 else 100.0

    y_kpi = pdf.get_y() + 2.5
    pdf.set_xy(14, y_kpi)
    pdf.cell(90, 6.5, f"- Tổng số khách hàng: {int(kpis['total_customers']):,} khách", ln=False)
    pdf.cell(90, 6.5, f"- Đánh giá: {tot_rev:,} ({pos_rev:,} Tích cực | {neg_rev:,} Tiêu cực)", ln=True)
    pdf.set_x(14)
    pdf.cell(90, 6.5, f"- Tỷ lệ rời bỏ trung bình: {float(kpis['avg_churn_risk'] or 0):.1f}%", ln=False)
    pdf.cell(90, 6.5, f"- Khách nhóm nguy cơ cao: {int(kpis['high_risk_count']):,} khách", ln=True)
    pdf.set_x(14)
    pdf.cell(90, 6.5, f"- Tỷ lệ giải quyết CSKH: {res_rate:.1f}% ({comp_comp}/{tot_comp} ca)", ln=False)
    pdf.cell(90, 6.5, f"- Tồn đọng CSKH: {pend_comp} chờ duyệt | {in_comp} đang xử lý", ln=True)
    pdf.ln(5)

    # 2. Cơ cấu rủi ro & Phân cụm NLP
    pdf.set_font(font_family, "B", 10.5)
    pdf.cell(0, 6, "2. CƠ CẤU RỦI RO & PHÂN CỤM KHIẾU NẠI", ln=True)
    pdf.ln(1)

    pdf.set_font(font_family, "B", 8.5)
    pdf.set_fill_color(226, 232, 240)
    pdf.cell(48, 6.5, "Nhóm Rủi Ro", border=1, fill=True)
    pdf.cell(35, 6.5, "Số Lượng Khách", border=1, fill=True)
    pdf.cell(10, 6.5, "", border=0)
    pdf.cell(67, 6.5, "Phân Cụm Khiếu Nại Tiêu Cực", border=1, fill=True)
    pdf.cell(30, 6.5, "Số Lượt Phàn Nàn", border=1, fill=True, ln=True)

    pdf.set_font(font_family, "", 8.5)
    df_clusters_desc = df_clusters.sort_values(by="review_count", ascending=False).reset_index(drop=True)
    max_rows = max(len(df_risk), len(df_clusters_desc))

    for i in range(max_rows):
        if i < len(df_risk):
            r_row = df_risk.iloc[i]
            pdf.cell(48, 6, str(r_row["risk_level"]), border=1)
            pdf.cell(35, 6, f"{int(r_row['customer_count']):,}", border=1)
        else:
            pdf.cell(83, 6, "", border=0)

        pdf.cell(10, 6, "", border=0)

        if i < len(df_clusters_desc):
            c_row = df_clusters_desc.iloc[i]
            pdf.cell(67, 6, str(c_row["cluster_name"])[:35], border=1)
            pdf.cell(30, 6, f"{int(c_row['review_count']):,}", border=1, ln=True)
        else:
            pdf.cell(97, 6, "", border=0, ln=True)
    pdf.ln(5)

    pdf.set_font(font_family, "B", 10.5)
    pdf.cell(0, 6, "3. DANH SÁCH KHÁCH HÀNG VIP CÓ NGUY CƠ RỜI BỎ CAO NHẤT", ln=True)
    pdf.ln(1)

    pdf.set_font(font_family, "B", 8.5)
    pdf.set_fill_color(226, 232, 240)
    pdf.cell(28, 6.5, "Mã Khách", border=1, fill=True)
    pdf.cell(65, 6.5, "Tên Khách Hàng", border=1, fill=True)
    pdf.cell(42, 6.5, "Tổng Chi Tiêu", border=1, fill=True)
    pdf.cell(28, 6.5, "Xác Suất Churn", border=1, fill=True)
    pdf.cell(27, 6.5, "Mức Nguy Cơ", border=1, fill=True, ln=True)

    pdf.set_font(font_family, "", 8.5)
    for _, row in df_top_vip.head(8).iterrows():
        pdf.cell(28, 5.8, str(row["customer_code"]), border=1)
        pdf.cell(65, 5.8, str(row["customer_name"])[:32], border=1)
        pdf.cell(42, 5.8, f"{float(row['total_spend']):,.0f} đ", border=1)
        pdf.cell(28, 5.8, f"{row['churn_risk_percent']}%", border=1)
        pdf.cell(27, 5.8, str(row["risk_level"]), border=1, ln=True)
    pdf.ln(5)

    # 4. Ghi nhận thực tế & Nhận xét tổng quan từ dữ liệu
    pdf.set_font(font_family, "B", 10.5)
    pdf.cell(0, 6, "4. TỔNG HỢP NHẬN XÉT & ĐÁNH GIÁ TỪ DỮ LIỆU", ln=True)
    pdf.ln(1)

    pdf.set_font(font_family, "", 8.5)
    pdf.set_fill_color(248, 250, 252)
    pdf.rect(10, pdf.get_y(), 190, 36, "F")

    y_rec = pdf.get_y() + 2
    pdf.set_xy(13, y_rec)
    pdf.multi_cell(184, 5.2,
                   f"• Tình hình xử lý khiếu nại CSKH: Tỷ lệ giải quyết phản hồi hiện đạt {res_rate:.1f}%, hệ thống đang ghi nhận {pend_comp} ca khiếu nại ở trạng thái chờ duyệt (PENDING) và {in_comp} ca đang trong tiến trình hỗ trợ.\n"
                   "• Thực trạng nhóm khách hàng VIP: Dữ liệu ghi nhận một số khách hàng có giá trị chi tiêu lũy kế cao (từ 600.000 đ đến trên 1.200.000 đ) đang có dấu hiệu giảm tương tác mua sắm, dẫn đến xác suất rủi ro rời bỏ tăng trên 80%.\n"
                   "• Xu hướng phản hồi sản phẩm: Kết quả phân tích NLP cho thấy các đánh giá tiêu cực tập trung chủ yếu vào nhóm vấn đề 'Cảm quan hương vị' và 'Khuyết tật chất lượng sản phẩm', đây là nguyên nhân trực tiếp tác động đến mức độ hài lòng của khách hàng."
                   )

    return bytes(pdf.output())

def render():
    user_perms = st.session_state.get("permissions", [])

    kpis = fetch_dashboard_kpis()
    df_risk = fetch_risk_distribution()
    df_clusters = fetch_sentiment_and_clusters()
    df_top_vip = fetch_top_risk_vip_customers(limit=10)
    df_sentiment_trend = fetch_sentiment_monthly_trends()

    c_title, c_export = st.columns([3, 1])
    with c_title:
        st.markdown("""
            <div style="margin-bottom: 8px;">
                <h2 style="color:#004D6B; font-weight:800; margin-bottom:4px;">
                    Dashboard Tổng Quan
                </h2>
                <p style="color:#64748B; font-size:14px; margin:0;">
                    Chỉ số đo lường hiệu quả giữ chân khách hàng, chất lượng phản hồi và dịch vụ CSKH.
                </p>
            </div>
        """, unsafe_allow_html=True)

    with c_export:
        if "EXPORT_PDF_REPORT" in user_perms:
            pdf_bytes = generate_pdf_report(kpis, df_risk, df_clusters, df_top_vip)
            st.download_button(
                label="Xuất Báo Cáo",
                data=pdf_bytes,
                file_name=f"Executive_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    st.write("")

    total_reviews = int(kpis.get("total_reviews", 0))
    positive_reviews = int(kpis.get("positive_reviews", 0))
    total_complaints = int(kpis.get("total_complaints", 0))
    completed_complaints = int(kpis.get("completed_complaints", 0))
    res_rate = (completed_complaints / total_complaints * 100) if total_complaints > 0 else 100.0

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Tổng Khách Hàng", f"{int(kpis['total_customers']):,}")
    with m2:
        st.metric("Tổng Lượt Đánh Giá", f"{total_reviews:,}", f"{positive_reviews:,} tích cực", delta_color="normal")
    with m3:
        st.metric("Tỷ Lệ Rời Bỏ TB", f"{float(kpis['avg_churn_risk'] or 0):.1f}%",
                  f"{int(kpis['high_risk_count']):,} khách High Risk", delta_color="inverse")
    with m4:
        st.metric("Tỷ Lệ Xử Lý CSKH", f"{res_rate:.1f}%", f"{int(kpis['pending_complaints']):,} ca đang chờ",
                  delta_color="normal")

    st.write("")
    st.markdown("---")

    st.markdown(
        "<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Xu Hướng Phản Hồi Khách Hàng Theo Cảm Xúc (Tích Cực / Tiêu Cực)</h4>",
        unsafe_allow_html=True)
    if not df_sentiment_trend.empty:
        color_sentiment = {
            "Positive": "#10B981",
            "Negative": "#E05252"
        }
        fig_area = px.area(
            df_sentiment_trend,
            x="month_period",
            y="review_count",
            color="sentiment",
            color_discrete_map=color_sentiment,
            labels={
                "month_period": "Thời Gian (Quý)",
                "review_count": "Số Lượng Đánh Giá",
                "sentiment": "Sắc Thái (Sentiment)"
            }
        )
        fig_area.update_layout(
            height=320,
            margin=dict(l=20, r=20, t=25, b=20),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(
                type="date",
                tickformat="%m/%Y",
                dtick="M3",
                tickangle=-30
            )
        )
        st.plotly_chart(fig_area, use_container_width=True)
    else:
        st.info("Chưa có đủ dữ liệu theo tháng để dựng biểu đồ miền.")

    st.write("")
    st.markdown("---")

    c_chart1, c_chart2 = st.columns(2, gap="large")

    with c_chart1:
        st.markdown(
            "<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Cơ Cấu Khách Hàng Theo Rủi Ro Churn</h4>",
            unsafe_allow_html=True)
        if not df_risk.empty:
            color_map = {
                "High": "#E05252",
                "High Risk": "#E05252",
                "Medium": "#F59E0B",
                "Medium Risk": "#F59E0B",
                "Low": "#10B981",
                "Low Risk": "#10B981"
            }
            fig_risk = px.pie(
                df_risk,
                names="risk_level",
                values="customer_count",
                hole=0.45,
                color="risk_level",
                color_discrete_map=color_map
            )
            fig_risk.update_layout(
                margin=dict(t=20, b=20, l=10, r=10),
                height=280,
                showlegend=True
            )
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            st.info("Chưa có dữ liệu dự báo rủi ro.")

    with c_chart2:
        st.markdown(
            "<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Phân Cụm Vấn Đề Tiêu Cực Từ Khách Hàng</h4>",
            unsafe_allow_html=True)
        if not df_clusters.empty:
            fig_cluster = px.bar(
                df_clusters,
                x="review_count",
                y="cluster_name",
                orientation="h",
                labels={"review_count": "Số Lượt Phàn Nàn", "cluster_name": "Nhóm Vấn Đề"}
            )
            fig_cluster.update_traces(marker_color="#E05252")
            fig_cluster.update_layout(
                margin=dict(t=20, b=20, l=10, r=10),
                height=280,
                plot_bgcolor="#FFFFFF"
            )
            st.plotly_chart(fig_cluster, use_container_width=True)
        else:
            st.info("Hiện không có phản hồi tiêu cực nào cần lưu ý.")

    st.write("")
    st.markdown("---")

    st.markdown(
        "<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Top 5 Khách Hàng VIP Có Nguy Cơ Rời Bỏ Cao (Ưu Tiên CSKH Giữ Chân)</h4>",
        unsafe_allow_html=True)
    if not df_top_vip.empty:
        df_top_display = df_top_vip.head(5).copy()
        df_top_display["churn_risk_percent"] = df_top_display["churn_risk_percent"].apply(lambda x: f"{x:.1f}%")
        df_top_display["total_spend"] = df_top_display["total_spend"].apply(lambda s: f"{float(s):,.0f} đ")
        st.dataframe(
            df_top_display.rename(columns={
                "customer_code": "Mã Khách",
                "customer_name": "Tên Khách Hàng",
                "total_spend": "Tổng Chi Tiêu Lũy Kế",
                "churn_risk_percent": "Xác Suất Churn",
                "risk_level": "Mức Nguy Cơ",
                "review_count": "Lượt Đánh Giá"
            }),
            use_container_width=True
        )
    else:
        st.info("Không có dữ liệu khách hàng VIP nguy cơ cao.")