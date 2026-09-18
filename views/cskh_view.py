import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import text
from myapp import app, db

def fetch_cskh_reviews(status_filter="PENDING", risk_filter="Tất cả", search_kw=""):
    conditions = ["1=1"]
    params = {}

    if status_filter == "PENDING":
        conditions.append("r.processing_status = 'PENDING'")
    elif status_filter == "IN_PROGRESS":
        conditions.append("r.processing_status = 'IN_PROGRESS'")
    elif status_filter == "COMPLETED":
        conditions.append("r.processing_status = 'COMPLETED'")
    elif status_filter == "NULL (Không cần xử lý)":
        conditions.append("r.processing_status IS NULL")

    if risk_filter != "Tất cả":
        conditions.append("pred.risk_level LIKE :risk")
        params["risk"] = f"%{risk_filter}%"

    if search_kw.strip():
        conditions.append("(c.name LIKE :kw OR c.customer_code LIKE :kw OR p.name LIKE :kw OR r.comment_text LIKE :kw)")
        params["kw"] = f"%{search_kw.strip()}%"

    where_clause = " AND ".join(conditions)

    query = text(f"""
        WITH LatestPred AS (
            SELECT customer_id, risk_level, churn_risk_percent,
                   ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY last_analyzed DESC) as rn
            FROM predictions
        )
        SELECT 
            r.id AS review_id,
            r.review_date,
            r.rating_stars,
            r.comment_text,
            r.cluster_name,
            r.sentiment,
            r.processing_status,
            r.processor_id,
            r.updated_at,
            c.id AS customer_id,
            c.customer_code,
            c.name AS customer_name,
            p.name AS product_name,
            pred.risk_level,
            ROUND(pred.churn_risk_percent, 1) AS churn_risk_percent
        FROM reviews r
        JOIN customers c ON r.customer_id = c.id
        JOIN products p ON r.product_id = p.id
        LEFT JOIN LatestPred pred ON pred.customer_id = c.id AND pred.rn = 1
        WHERE {where_clause}
        ORDER BY r.review_date DESC
    """)

    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn, params=params)


def update_review_status(review_id, new_status, processor_id=None):
    query = text("""
        UPDATE reviews
        SET processing_status = :status,
            processor_id = :processor_id,
            updated_at = :updated_at
        WHERE id = :review_id
    """)
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(query, {
                "status": new_status,
                "processor_id": processor_id,
                "updated_at": datetime.now(),
                "review_id": review_id
            })


def render():
    st.markdown("""
        <div style="margin-bottom: 18px;">
            <h2 style="color:#004D6B; font-weight:800; margin-bottom:4px;">
                Quản Lý Đánh Giá & Dịch Vụ CSKH
            </h2>
            <p style="color:#64748B; font-size:14px; margin:0;">
                Giám sát phản hồi, liên kết nguy cơ rời bỏ và phân loại tiến độ hỗ trợ khách hàng.
            </p>
        </div>
    """, unsafe_allow_html=True)

    f1, f2, f3 = st.columns([1.2, 1, 2])
    with f1:
        status_choice = st.selectbox(
            "Trạng thái xử lý:",
            ["PENDING", "IN_PROGRESS", "COMPLETED", "Tất cả", "NULL (Không cần xử lý)"]
        )
    with f2:
        risk_choice = st.selectbox(
            "Mức rủi ro Churn:",
            ["Tất cả", "High", "Medium", "Low"]
        )
    with f3:
        search_kw = st.text_input(
            "Tìm kiếm tổng hợp:",
            placeholder="Nhập tên khách hàng, mã, sản phẩm hoặc từ khóa..."
        )

    df_reviews = fetch_cskh_reviews(status_choice, risk_choice, search_kw)

    st.write("")
    st.markdown(f"**Danh sách phản hồi:** `{len(df_reviews):,}` kết quả phù hợp")

    if df_reviews.empty:
        st.info("Không tìm thấy dữ liệu đánh giá thỏa mãn điều kiện lọc.")
        return

    df_show = df_reviews.copy()
    df_show["rating_stars"] = df_show["rating_stars"].apply(lambda s: f"{s:.1f}" if pd.notna(s) else "—")
    df_show["churn_risk_percent"] = df_show["churn_risk_percent"].apply(lambda p: f"{p}%" if pd.notna(p) else "—")
    df_show["processing_status"] = df_show["processing_status"].fillna("—")

    st.dataframe(
        df_show[[
            "review_id", "review_date", "customer_name", "product_name",
            "rating_stars", "cluster_name", "risk_level", "churn_risk_percent",
            "processing_status", "comment_text"
        ]].rename(columns={
            "review_id": "ID",
            "review_date": "Thời Gian",
            "customer_name": "Khách Hàng",
            "product_name": "Sản Phẩm",
            "rating_stars": "Sao",
            "cluster_name": "Phân Cụm Vấn Đề",
            "risk_level": "Nguy Cơ Churn",
            "churn_risk_percent": "% Rủi Ro",
            "processing_status": "Trạng Thái",
            "comment_text": "Nội Dung Bình Luận"
        }),
        use_container_width=True,
        height=330
    )

    st.write("")


    user_perms = st.session_state.get("permissions", [])

    if "UPDATE_CSKH_STATUS" in user_perms:
        st.markdown(
            "<h3 style='color:#004D6B; font-size:18px; font-weight:700;'>Cập Nhật Trạng Thái Xử Lý Khiếu Nại</h3>",
            unsafe_allow_html=True)

        actionable_df = df_reviews[df_reviews["processing_status"].isin(["PENDING", "IN_PROGRESS"])]

        if actionable_df.empty:
            st.success("Không có khiếu nại nào cần xử lý trong danh sách lọc!")
        else:
            with st.form("form_update_cskh"):
                col_form1, col_form2, col_form3 = st.columns([1.5, 1, 1])

                review_options = {
                    row[
                        "review_id"]: f"ID #{row['review_id']} - {row['customer_name']} ({row['cluster_name'] or 'Khiếu nại'})"
                    for _, row in actionable_df.iterrows()
                }

                with col_form1:
                    selected_review_id = st.selectbox(
                        "Chọn khiếu nại cần duyệt:",
                        options=list(review_options.keys()),
                        format_func=lambda x: review_options[x]
                    )

                with col_form2:
                    new_status = st.selectbox(
                        "Trạng thái mới:",
                        ["COMPLETED", "IN_PROGRESS", "PENDING"]
                    )

                with col_form3:
                    user_dict = st.session_state.get("user", {})
                    processor_id = user_dict.get("id", 1)
                    st.text_input("ID nhân viên xử lý (processor_id):", value=str(processor_id), disabled=True)

                submitted = st.form_submit_button("Xác Nhận Cập Nhật", use_container_width=True)

                if submitted:
                    target_row = df_reviews[df_reviews["review_id"] == selected_review_id].iloc[0]
                    is_positive = (
                            target_row.get("sentiment") == "Positive"
                            or target_row.get("cluster_name") == "Hài lòng / Không có khiếu nại"
                            or (pd.isna(target_row.get("processing_status")) and target_row.get("rating_stars") == 5)
                    )

                    if is_positive:
                        st.error(
                            "Đây là đánh giá tích cực/hài lòng, không thuộc quy trình khiếu nại CSKH!")
                    else:
                        try:
                            update_review_status(selected_review_id, new_status, processor_id)
                            st.success(
                                f"Đã cập nhật thành công đánh giá ID #{selected_review_id} sang trạng thái `{new_status}`!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi cập nhật vào CSDL: {e}")
    else:
        st.info("Bạn chỉ có quyền xem danh sách đánh giá. Chức năng cập nhật trạng thái khiếu nại đã bị khóa theo phân quyền tài khoản.")