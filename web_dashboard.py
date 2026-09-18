import streamlit as st
import pandas as pd
from sqlalchemy import text
from werkzeug.security import check_password_hash
from myapp import app, db
from views import dashboard_view, churn_view, cskh_view, crawler_view, authorization_view

st.set_page_config(
    page_title="E-Commerce Churn Intelligence",
    layout="wide",
    initial_sidebar_state="expanded"
)

CUSTOM_STYLE = """
<style>
    .stApp {
        background-color: #F8FAFC;
        color: #0F172A;
    }

    div[data-testid="stForm"] {
        background-color: #FFFFFF !important;
        border-radius: 16px !important;
        padding: 36px 32px !important;
        box-shadow: 0 10px 25px rgba(0, 77, 107, 0.06) !important;
        border: 1px solid #E2E8F0 !important;
    }

    div[data-baseweb="input"] {
        border-radius: 8px !important;
        border: 1px solid #CBD5E1 !important;
        background-color: #FFFFFF !important;
    }
    div[data-baseweb="input"]:focus-within {
        border-color: #0081B3 !important;
        box-shadow: 0 0 0 1px #0081B3 !important;
    }

    div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg, #0081B3 0%, #00668E 100%) !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        padding: 10px 0 !important;
        border: none !important;
        box-shadow: 0 4px 12px rgba(0, 129, 179, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stFormSubmitButton"] > button:hover {
        background: linear-gradient(135deg, #00668E 0%, #004D6B 100%) !important;
        box-shadow: 0 6px 16px rgba(0, 77, 107, 0.35) !important;
    }

    .login-logo {
        text-align: center;
        font-size: 26px;
        font-weight: 800;
        color: #004D6B;
        margin-bottom: 6px;
        letter-spacing: -0.5px;
    }
    .login-subheading {
        text-align: center;
        font-size: 14px;
        color: #64748B;
        margin-bottom: 24px;
    }

    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-right: 1px solid #E2E8F0 !important;
        padding-top: 1.2rem;
    }
    [data-testid="stSidebar"] div[data-testid="stRadio"] > label {
        display: none !important;
    }
    [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label {
        background-color: transparent !important;
        padding: 9px 14px !important;
        border-radius: 8px !important;
        margin-bottom: 4px !important;
        transition: all 0.2s ease !important;
        border: 1px solid transparent !important;
        cursor: pointer !important;
    }
    [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label:hover {
        background-color: #F1F5F9 !important;
    }
    [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label p {
        font-size: 13.5px !important;
        font-weight: 500 !important;
        color: #334155 !important;
    }
    /* Ẩn dấu radio circle mặc định */
    [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] input[type="radio"],
    [data-testid="stSidebar"] div[data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }

    div.stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        border: 1px solid #CBD5E1 !important;
        color: #475569 !important;
        background-color: #FFFFFF !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button:hover {
        border-color: #EF4444 !important;
        color: #EF4444 !important;
        background-color: #FEF2F2 !important;
    }
</style>
"""
st.markdown(CUSTOM_STYLE, unsafe_allow_html=True)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.permissions = []

def authenticate_user(email, plain_password):
    query_user = text("""
        SELECT u.id, u.email, u.password, u.full_name, u.role_id, r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.email = :email
    """)
    try:
        with app.app_context():
            with db.engine.connect() as conn:
                result = conn.execute(query_user, {"email": email})
                user_row = result.fetchone()

                if not user_row:
                    return None, "Email không tồn tại trên hệ thống."

                if not check_password_hash(user_row[2], plain_password):
                    return None, "Mật khẩu không chính xác."

                query_perms = text("""
                    SELECT p.code
                    FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id = :role_id
                """)
                perm_rows = conn.execute(query_perms, {"role_id": user_row[4]}).fetchall()
                permissions = [p[0] for p in perm_rows]

                user_info = {
                    "id": user_row[0],
                    "email": user_row[1],
                    "full_name": user_row[3],
                    "role_id": user_row[4],
                    "role_name": user_row[5]
                }
                return user_info, permissions
    except Exception as e:
        return None, f"Lỗi CSDL: {str(e)}"

def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.permissions = []
    st.rerun()

def render_login_page():
    st.write("")
    st.write("")

    _, col_center, _ = st.columns([1, 1.1, 1])

    with col_center:
        st.markdown("""
            <div class="login-logo">E-Commerce Churn Intelligence</div>
            <div class="login-subheading">Vui lòng sử dụng tài khoản được cấp quyền để truy cập</div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            input_email = st.text_input("Email", placeholder="e.g. admin@gmail.com")
            input_password = st.text_input("Password", type="password", placeholder="e.g. 12345")

            st.write("")
            btn_submit = st.form_submit_button("Đăng nhập", use_container_width=True)

            if btn_submit:
                if not input_email.strip() or not input_password.strip():
                    st.warning("Vui lòng nhập đầy đủ Email và Mật khẩu.")
                else:
                    user_info, perms = authenticate_user(input_email.strip(), input_password.strip())
                    if user_info:
                        st.session_state.logged_in = True
                        st.session_state.user = user_info
                        st.session_state.permissions = perms
                        st.rerun()
                    else:
                        st.error(perms)

def render_main_app():
    user = st.session_state.user
    perms = st.session_state.permissions

    with st.sidebar:
        st.markdown("""
            <div style="padding: 10px 4px 18px 4px; border-bottom: 1px solid #E2E8F0; margin-bottom: 16px;">
                <div style="font-size: 17px; font-weight: 800; color: #004D6B; letter-spacing: -0.4px;">
                    HOME
                </div>
                <div style="font-size: 12px; color: #64748B; margin-top: 2px;">
                    E-Commerce Analytics
                </div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="padding: 10px 14px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; margin-bottom: 16px;">
                <div style="font-size: 13.5px; font-weight: 700; color: #0F172A;">{user['full_name']}</div>
                <div style="font-size: 11.5px; color: #0081B3; font-weight: 600; text-transform: uppercase;">{user['role_name']}</div>
            </div>
        """, unsafe_allow_html=True)

        st.markdown("""
            <div style="font-size: 11px; font-weight: 700; color: #94A3B8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">
                Các Chức Năng
            </div>
        """, unsafe_allow_html=True)

        menu_options = []

        if "VIEW_DASHBOARD" in perms:
            menu_options.append("Dashboard tổng quan")

        if "VIEW_CHURN_PREDICTION" in perms:
            menu_options.append("Dự báo tỷ lệ khách rời bỏ")

        if "VIEW_CUSTOMER_REVIEWS" in perms:
            menu_options.append("Đánh giá & CSKH")

        if "TOGGLE_CRAWLER" in perms:
            menu_options.append("Cào dữ liệu")

        if any(p in perms for p in ["CREATE_USER", "EDIT_USER_PERMISSIONS", "DELETE_USER"]):
            menu_options.append("Phân quyền")

        if not menu_options:
            st.warning("Tài khoản của bạn hiện chưa được cấp quyền truy cập chức năng nào.")
            selected_page = None
        else:
            selected_page = st.radio("Điều hướng phân hệ:", menu_options)

        st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
        if st.button("Đăng xuất", use_container_width=True):
            logout()

    if selected_page == "Dashboard tổng quan":
        dashboard_view.render()

    elif selected_page == "Dự báo tỷ lệ khách rời bỏ":
        churn_view.render()

    elif selected_page == "Đánh giá & CSKH":
        cskh_view.render()

    elif selected_page == "Cào dữ liệu":
        crawler_view.render()

    elif selected_page == "Phân quyền":
        authorization_view.render()

if not st.session_state.logged_in:
    render_login_page()
else:
    render_main_app()