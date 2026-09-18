import streamlit as st
import time
from datetime import datetime
from myapp.crawler import run_full_pipeline


def render():
    user_perms = st.session_state.get("permissions", [])
    if "TOGGLE_CRAWLER" not in user_perms:
        st.error("Bạn không có quyền truy cập chức năng này (yêu cầu quyền TOGGLE_CRAWLER).")
        return

    if "last_crawled_at" not in st.session_state:
        st.session_state.last_crawled_at = "Chưa có lượt chạy gần đây"

    st.markdown("""
        <div style="margin-bottom: 24px;">
            <h2 style="color:#004D6B; font-weight:800; margin-bottom:4px;">
                Thu Thập & Xử Lý Dữ Liệu Tự Động
            </h2>
            <p style="color:#64748B; font-size:14px; margin:0;">
                Kích hoạt chu trình khép kín: Cào đánh giá từ Tiki ➔ Tiền xử lý NLP & Phân loại cảm xúc ➔ Dự báo rủi ro rời bỏ (Churn).
            </p>
        </div>
    """, unsafe_allow_html=True)

    col_left, col_right = st.columns([1.3, 1], gap="large")

    with col_left:
        st.markdown(
            "<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Kích Hoạt Chu Trình Xử Lý (Pipeline)</h4>",
            unsafe_allow_html=True)
        st.caption(
            "Bấm nút bên dưới để hệ thống tự động thực hiện toàn bộ các bước và lưu trực tiếp vào cơ sở dữ liệu.")

        if st.button("Bắt Đầu Thu Thập & Phân Tích Dữ Liệu", use_container_width=True, type="primary"):
            status_placeholder = st.empty()
            progress_bar = st.progress(0)

            def update_progress(msg):
                status_placeholder.info(f"{msg}")

            try:
                progress_bar.progress(10)
                update_progress("Đang kết nối API và quét dữ liệu sản phẩm, bình luận...")

                run_full_pipeline(progress_callback=update_progress)

                progress_bar.progress(100)
                st.session_state.last_crawled_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                status_placeholder.empty()
                progress_bar.empty()
                st.success("Toàn bộ quy trình (Cào dữ liệu ➔ Phân loại khía cạnh lỗi ➔ Dự báo Churn) đã hoàn tất!")
                time.sleep(1.5)
                st.rerun()
            except Exception as e:
                status_placeholder.empty()
                progress_bar.empty()
                st.error(f"Lỗi phát sinh trong tiến trình: {e}")

    with col_right:
        with st.container(border=True):
            st.caption("CHẾ ĐỘ VẬN HÀNH")
            st.markdown("<h3 style='color:#10B981; margin-top:-8px; font-weight:800;'>HỆ THỐNG</h3>",
                        unsafe_allow_html=True)

            st.caption("LẦN CHẠY GẦN NHẤT")
            st.markdown(f"**{st.session_state.last_crawled_at}**")

            st.divider()

            st.markdown("""
            **Quy trình tự động gồm:**
            1. Quét sản phẩm & reviews từ gian hàng.
            2. Phân loại cảm xúc & trích xuất khía cạnh (NLP).
            3. Tính 7 thuộc tính RFM & dự báo tỷ lệ rời bỏ (ML).
            """)