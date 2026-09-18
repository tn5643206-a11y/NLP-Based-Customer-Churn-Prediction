import streamlit as st
import pandas as pd
from sqlalchemy import text
from werkzeug.security import generate_password_hash
from myapp import app, db

def fetch_roles():
    query = text("SELECT id, name FROM roles ORDER BY id")
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)

def create_role(role_name):
    query = text("INSERT INTO roles (name) VALUES (:name)")
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(query, {"name": role_name})

def delete_role(role_id):
    # Kiểm tra còn user nào thuộc role này không
    check_user_query = text("SELECT COUNT(*) FROM users WHERE role_id = :role_id")
    del_role_perms_query = text("DELETE FROM role_permissions WHERE role_id = :role_id")
    del_role_query = text("DELETE FROM roles WHERE id = :role_id")

    with app.app_context():
        with db.engine.begin() as conn:
            count = conn.execute(check_user_query, {"role_id": role_id}).scalar()
            if count > 0:
                raise Exception(f"Không thể xóa vai trò này vì còn {count} tài khoản người dùng đang được gán!")
            conn.execute(del_role_perms_query, {"role_id": role_id})
            conn.execute(del_role_query, {"role_id": role_id})

def fetch_permissions():
    query = text("SELECT id, code, description FROM permissions ORDER BY id")
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)


def fetch_role_permissions(role_id):
    query = text("SELECT permission_id FROM role_permissions WHERE role_id = :role_id")
    with app.app_context():
        with db.engine.connect() as conn:
            rows = conn.execute(query, {"role_id": role_id}).fetchall()
            return [r[0] for r in rows]

def update_role_permissions(role_id, permission_ids):
    del_query = text("DELETE FROM role_permissions WHERE role_id = :role_id")
    ins_query = text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id)")
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(del_query, {"role_id": role_id})
            for pid in permission_ids:
                conn.execute(ins_query, {"role_id": role_id, "permission_id": pid})

def fetch_users():
    query = text("""
        SELECT u.id, u.email, u.full_name, r.name as role_name, u.role_id
        FROM users u
        JOIN roles r ON u.role_id = r.id
        ORDER BY u.id
    """)
    with app.app_context():
        with db.engine.connect() as conn:
            return pd.read_sql(query, conn)

def create_user(email, plain_password, full_name, role_id):
    hashed = generate_password_hash(plain_password)
    query = text("""
        INSERT INTO users (email, password, full_name, role_id)
        VALUES (:email, :password, :full_name, :role_id)
    """)
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(query, {
                "email": email,
                "password": hashed,
                "full_name": full_name,
                "role_id": role_id
            })

def delete_user(user_id):
    query = text("DELETE FROM users WHERE id = :user_id")
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(query, {"user_id": user_id})

def render():
    st.markdown("""
        <div style="margin-bottom: 20px;">
            <h2 style="color:#004D6B; font-weight:800; margin-bottom:4px;">
                Quản Trị Phân Quyền
            </h2>
            <p style="color:#64748B; font-size:14px; margin:0;">
                Gán quyền động cho các vai trò, quản lý cơ cấu vai trò và tài khoản người dùng hệ thống.
            </p>
        </div>
    """, unsafe_allow_html=True)

    tab_roles, tab_users = st.tabs(["Cấp Quyền Theo Vai Trò", "Quản Lý Tài Khoản Người Dùng"])

    with tab_roles:
        df_roles = fetch_roles()
        df_perms = fetch_permissions()
        role_mapping = dict(zip(df_roles["name"], df_roles["id"]))

        st.markdown("<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Cấu Hình Quyền Hạn</h4>",
                    unsafe_allow_html=True)
        selected_role_name = st.selectbox("Chọn vai trò cần chỉnh sửa quyền:", list(role_mapping.keys()))
        selected_role_id = role_mapping[selected_role_name]
        current_perm_ids = fetch_role_permissions(selected_role_id)

        st.markdown(
            "<p style='font-size:13.5px; font-weight:600; color:#334155; margin-top:8px;'>Danh sách quyền hạn khả dụng:</p>",
            unsafe_allow_html=True)
        with st.form("form_update_role_perms"):
            selected_ids = []
            cols = st.columns(2)
            for idx, row in df_perms.iterrows():
                col = cols[idx % 2]
                label_text = f"**{row['code']}** - {row['description'] or ''}"
                checked = row["id"] in current_perm_ids
                if col.checkbox(label_text, value=checked, key=f"perm_{row['id']}"):
                    selected_ids.append(row["id"])

            st.write("")
            if st.form_submit_button("Lưu Thay Đổi Phân Quyền", use_container_width=True):
                try:
                    update_role_permissions(selected_role_id, selected_ids)
                    st.success(f"Đã cập nhật quyền thành công cho vai trò: {selected_role_name}!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Lỗi khi lưu phân quyền: {e}")

        st.write("")
        st.markdown("---")

        st.markdown("<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Quản Lý Vai Trò</h4>",
                    unsafe_allow_html=True)
        c_role_add, c_role_del = st.columns(2, gap="large")

        with c_role_add:
            with st.form("form_add_role"):
                st.markdown("**Thêm vai trò mới**")
                new_role_input = st.text_input("Tên vai trò mới:", placeholder="e.g. Analyst...")
                if st.form_submit_button("Thêm Vai Trò", use_container_width=True):
                    if not new_role_input.strip():
                        st.warning("Vui lòng nhập tên vai trò.")
                    else:
                        try:
                            create_role(new_role_input.strip())
                            st.success(f"Đã tạo thành công vai trò: `{new_role_input.strip()}`!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi thêm vai trò (có thể tên đã trùng): {e}")

        with c_role_del:
            with st.form("form_delete_role"):
                st.markdown("**Xóa vai trò**")
                deletable_roles = [r for r in role_mapping.keys() if r.lower() != "admin"]
                del_role_target = st.selectbox("Chọn vai trò cần xóa:",
                                               deletable_roles if deletable_roles else ["Không có vai trò hợp lệ"])
                if st.form_submit_button("Xóa Vai Trò Đã Chọn", use_container_width=True):
                    if not deletable_roles:
                        st.warning("Không có vai trò phụ nào để xóa.")
                    else:
                        try:
                            delete_role(role_mapping[del_role_target])
                            st.success(f"Đã xóa vai trò: `{del_role_target}`!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Thao tác thất bại: {e}")

    with tab_users:
        df_users = fetch_users()
        df_roles = fetch_roles()
        role_mapping = dict(zip(df_roles["name"], df_roles["id"]))
        current_logged_id = st.session_state.get("user", {}).get("id")

        st.markdown("<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Danh Sách Tài Khoản</h4>",
                    unsafe_allow_html=True)
        st.dataframe(
            df_users[["id", "full_name", "email", "role_name"]].rename(columns={
                "id": "ID",
                "full_name": "Họ và Tên",
                "email": "Email Đăng Nhập",
                "role_name": "Vai Trò"
            }),
            use_container_width=True,
            height=200
        )

        st.write("")
        st.markdown("---")

        c_user_add, c_user_del = st.columns([1.3, 1], gap="large")

        # THÊM TÀI KHOẢN MỚI
        with c_user_add:
            st.markdown("<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Thêm Tài Khoản Mới</h4>",
                        unsafe_allow_html=True)
            with st.form("form_create_user"):
                c1, c2 = st.columns(2)
                with c1:
                    new_fullname = st.text_input("Họ và Tên:", placeholder="VD: Nguyễn Văn A")
                    new_email = st.text_input("Email Đăng Nhập:", placeholder="VD: nva@gmail.com")
                with c2:
                    new_password = st.text_input("Mật khẩu:", type="password", placeholder="Nhập mật khẩu...")
                    new_role = st.selectbox("Vai trò gán cho tài khoản:", list(role_mapping.keys()))

                if st.form_submit_button("Tạo Tài Khoản Mới", use_container_width=True):
                    if not new_email.strip() or not new_password.strip() or not new_fullname.strip():
                        st.warning("Vui lòng điền đầy đủ các trường thông tin.")
                    else:
                        try:
                            create_user(new_email.strip(), new_password.strip(), new_fullname.strip(),
                                        role_mapping[new_role])
                            st.success(f"Đã tạo thành công tài khoản `{new_email}`!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi thêm người dùng (có thể email đã tồn tại): {e}")

        with c_user_del:
            st.markdown("<h4 style='color:#004D6B; font-size:16px; font-weight:700;'>Xóa Tài Khoản</h4>",
                        unsafe_allow_html=True)
            other_users = df_users[df_users["id"] != current_logged_id]

            user_options = {
                row["id"]: f"#{row['id']} - {row['full_name']} ({row['email']})"
                for _, row in other_users.iterrows()
            }

            if not user_options:
                st.info("Không có tài khoản nào khác để xóa.")
            else:
                with st.form("form_delete_user"):
                    selected_del_id = st.selectbox(
                        "Chọn tài khoản cần xóa:",
                        options=list(user_options.keys()),
                        format_func=lambda x: user_options[x]
                    )
                    st.caption("Cảnh báo: Hành động này sẽ xóa hoàn toàn tài khoản khỏi cơ sở dữ liệu.")

                    if st.form_submit_button("Xác Nhận Xóa Tài Khoản", use_container_width=True):
                        try:
                            delete_user(selected_del_id)
                            st.success(f"Đã xóa thành công tài khoản ID #{selected_del_id}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Lỗi khi xóa người dùng: {e}")