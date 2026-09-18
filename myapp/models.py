from datetime import datetime
from sqlalchemy.sql import func
from enum import Enum as PyEnum
from flask_login import UserMixin
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Unicode, UnicodeText
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash

from myapp import app, db

class BaseModel(db.Model):
    __abstract__ = True
    id = Column(Integer, primary_key=True, autoincrement=True)

class ProcessingStatus(PyEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN PROGRESS"
    COMPLETED = "COMPLETED"

class RiskLevel(PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class RolePermission(db.Model):
    __tablename__ = "role_permissions"
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id = Column(Integer, ForeignKey("permissions.id"), primary_key=True)

class Permission(BaseModel):
    __tablename__ = "permissions"
    code = Column(String(50), unique=True, nullable=False)
    description = Column(Unicode(255), nullable=True)

class Role(BaseModel):
    __tablename__ = "roles"
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Unicode(255), nullable=True)

    permissions = relationship("Permission", secondary="role_permissions", lazy="subquery", backref="roles")
    users = relationship("User", backref="role", lazy=True)

class User(BaseModel, UserMixin):
    __tablename__ = "users"
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    full_name = Column(Unicode(100), nullable=False)

    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    processed_reviews = relationship("Review", backref="processor", lazy=True)

    def has_permission(self, perm_code):
        return any(perm.code == perm_code for perm in self.role.permissions) if self.role else False

class Product(BaseModel):
    __tablename__ = "products"
    product_code = Column(String(50), unique=True, nullable=True)
    name = Column(Unicode(255), nullable=False)
    price = Column(BigInteger, default=0)
    quantity_sold = Column(Integer, default=0)

    reviews = relationship("Review", backref="product", lazy="dynamic")


class Customer(BaseModel):
    __tablename__ = "customers"
    customer_code = Column(String(50), unique=True, nullable=True)
    name = Column(Unicode(100), nullable=False)
    created_at = Column(DateTime, default=func.now())

    reviews = relationship("Review", backref="customer", lazy="dynamic")
    predictions = relationship("Prediction", backref="customer", lazy="dynamic")

class Review(BaseModel):
    __tablename__ = "reviews"
    rating_stars = Column(Integer, nullable=True)
    comment_text = Column(UnicodeText, nullable=False)
    review_date = Column(DateTime, default=func.now())
    sentiment = Column(Unicode(50), nullable=True)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    cluster_id = Column(Integer, nullable=True)
    cluster_name = Column(Unicode(100), nullable=True)
    processing_status = Column(Enum(ProcessingStatus), nullable=True)
    processor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, onupdate=func.now())

class Prediction(BaseModel):
    __tablename__ = "predictions"
    churn_risk_percent = Column(Float, nullable=False)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW, nullable=False)
    last_analyzed = Column(DateTime, default=func.now())

    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

def seed_data():
    perms = [
        Permission(code="CREATE_USER", description="Tạo tài khoản người dùng"),
        Permission(code="EDIT_USER_PERMISSIONS", description="Sửa, gán thêm hoặc xóa bớt quyền người dùng"),
        Permission(code="DELETE_USER", description="Xóa tài khoản người dùng"),
        Permission(code="TOGGLE_CRAWLER", description="Bật (tắt) tính năng cào data"),
        Permission(code="VIEW_DASHBOARD", description="Xem màn hình Dashboard tổng quan"),
        Permission(code="VIEW_CHURN_PREDICTION", description="Xem dự báo Churn Risk"),
        Permission(code="VIEW_CUSTOMER_REVIEWS", description="Xem danh sách khách hàng kèm bình luận có Risk Level"),
        Permission(code="UPDATE_CSKH_STATUS", description="Cập nhật tiến độ xử lý CSKH"),
        Permission(code="EXPORT_PDF_REPORT", description="Xuất báo cáo thành PDF"),
    ]

    db.session.add_all(perms)
    db.session.commit()

    p = {perm.code: perm for perm in Permission.query.all()}

    role_admin = Role(name="Admin", description="Quản trị viên toàn quyền")
    role_admin.permissions = list(p.values())

    role_manager = Role(name="Manager", description="Xem báo cáo và phân tích")
    role_manager.permissions = [
        p["TOGGLE_CRAWLER"],
        p["VIEW_DASHBOARD"],
        p["VIEW_CHURN_PREDICTION"],
        p["VIEW_CUSTOMER_REVIEWS"],
        p["EXPORT_PDF_REPORT"],
    ]

    role_staff = Role(name="Staff", description="Xử lý khiếu nại khách hàng")
    role_staff.permissions = [
        p["VIEW_CUSTOMER_REVIEWS"],
        p["UPDATE_CSKH_STATUS"],
    ]

    db.session.add_all([role_admin, role_manager, role_staff])
    db.session.commit()

    admin_user = User(
        email="admin@gmail.com",
        password=generate_password_hash("admin123"),
        full_name="System Administrator",
        role_id=role_admin.id
    )
    db.session.add(admin_user)
    db.session.commit()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not Permission.query.first():
            seed_data()