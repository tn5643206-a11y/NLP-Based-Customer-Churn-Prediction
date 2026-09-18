import os
import joblib
import pandas as pd
import numpy as np
from sqlalchemy import text
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix
from myapp import app, db

# 7 đặc trưng độc lập: hành vi, độ dài phản hồi và 4 khía cạnh khiếu nại NLP
FEATURES = [
    'total_reviews',
    'avg_product_price',
    'avg_comment_length',
    'complaint_quality_cnt',
    'complaint_shipping_cnt',
    'complaint_packaging_cnt',
    'complaint_taste_cnt'
]


def load_data() -> pd.DataFrame:
    query = text("""
        SELECT
            r.id AS review_id,
            r.customer_id,
            c.customer_code,
            c.name AS customer_name,
            r.product_id,
            p.price AS product_price,
            r.rating_stars,
            r.comment_text,
            r.sentiment,
            r.cluster_id,
            r.cluster_name,
            r.review_date
        FROM reviews r
        JOIN customers c on c.id = r.customer_id 
        LEFT JOIN products p on p.id = r.product_id
    """)

    with app.app_context():
        with db.engine.connect() as conn:
            df_clean = pd.read_sql(query, conn)
    print(f"Tải thành công {len(df_clean)} dòng dữ liệu từ CSDL!")
    return df_clean


def extract_customer_features(df: pd.DataFrame) -> pd.DataFrame:
    df['review_date'] = pd.to_datetime(df['review_date'])
    date = df['review_date'].max()

    df['is_negative'] = (df['sentiment'] == 'Negative').astype(int)
    df['is_quality_complaint'] = (df['cluster_id'] == 1).astype(int)
    df['is_shipping_complaint'] = (df['cluster_id'] == 0).astype(int)
    df['is_packaging_complaint'] = (df['cluster_id'] == 3).astype(int)
    df['is_taste_complaint'] = (df['cluster_id'] == 2).astype(int)

    # Tính độ dài bình luận theo số từ
    df['comment_word_count'] = df['comment_text'].fillna('').apply(lambda x: len(str(x).split()))

    customer_agg = df.groupby(['customer_id', 'customer_code', 'customer_name']).agg(
        last_review_date=('review_date', 'max'),
        total_reviews=('review_id', 'count'),
        avg_rating_stars=('rating_stars', 'mean'),
        count_negative=('is_negative', 'sum'),
        complaint_quality_cnt=('is_quality_complaint', 'sum'),
        complaint_shipping_cnt=('is_shipping_complaint', 'sum'),
        complaint_packaging_cnt=('is_packaging_complaint', 'sum'),
        complaint_taste_cnt=('is_taste_complaint', 'sum'),
        avg_product_price=('product_price', 'mean'),
        avg_comment_length=('comment_word_count', 'mean')
    ).reset_index()

    customer_agg['recency_days'] = (date - customer_agg['last_review_date']).dt.days
    customer_agg['negative_ratio'] = (customer_agg['count_negative'] / customer_agg['total_reviews']).round(3)
    customer_agg['avg_rating_stars'] = customer_agg['avg_rating_stars'].fillna(0).round(2)
    customer_agg['avg_product_price'] = customer_agg['avg_product_price'].fillna(0).round(0)
    customer_agg['avg_comment_length'] = customer_agg['avg_comment_length'].round(1)

    columns = [
        'customer_id', 'customer_code', 'customer_name', 'recency_days',
        'total_reviews', 'avg_rating_stars', 'negative_ratio',
        'complaint_quality_cnt', 'complaint_shipping_cnt', 'complaint_packaging_cnt',
        'complaint_taste_cnt', 'avg_product_price', 'avg_comment_length'
    ]
    return customer_agg[columns]


def create_churn_labels(df_features: pd.DataFrame) -> pd.DataFrame:
    df = df_features.copy()
    recency_threshold = df['recency_days'].quantile(0.4)

    churn_condition = ((df['recency_days'] > recency_threshold) |
                       (df['avg_rating_stars'] <= 2) | (df['negative_ratio'] >= 0.5))
    df['churn'] = churn_condition.astype(int)
    return df


CHURN_MODEL = os.path.join(os.path.dirname(__file__), 'churn_model.pkl')


def train_churn_model(df_labeled: pd.DataFrame):
    X = df_labeled[FEATURES]
    y = df_labeled['churn']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y)

    rf_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42
    )
    rf_model.fit(X_train, y_train)

    y_pred = rf_model.predict(X_test)
    y_prob = rf_model.predict_proba(X_test)[:, 1]

    print("\n--- KẾT QUẢ ĐÁNH GIÁ (30% TEST) ---")
    print(classification_report(y_test, y_pred, target_names=['Loyal (0)', 'Churn (1)']))
    print(f"AUC-ROC Score: {roc_auc_score(y_test, y_prob):.4f}")
    print("Ma trận nhầm lẫn (Confusion matrix):")
    cm = confusion_matrix(y_test, y_pred)
    print(f"                        Dự đoán Ở lại (0)      Dự đoán Rời bỏ (1)")
    print(f"Thực tế Ở LẠI (0)  :   {cm[0, 0]:<20} {cm[0, 1]:<20}")
    print(f"Thực tế RỜI BỎ (1) :   {cm[1, 0]:<20} {cm[1, 1]:<20}")

    joblib.dump(rf_model, CHURN_MODEL)
    print(f"Đã lưu model tại: {CHURN_MODEL}")
    return rf_model


def save_predictions_to_db(df_features: pd.DataFrame, model):
    X_all = df_features[FEATURES]
    df_pred = df_features.copy()

    df_pred["churn_risk_percent"] = (model.predict_proba(X_all)[:, 1] * 100).round(2)

    def categorize_risk(risk_pct):
        if risk_pct >= 70:
            return "High"
        elif risk_pct >= 40:
            return "Medium"
        else:
            return "Low"

    df_pred["risk_level"] = df_pred["churn_risk_percent"].apply(categorize_risk)
    df_pred["last_analyzed"] = pd.Timestamp.now()

    cols = [
        "customer_id",
        "churn_risk_percent",
        "risk_level",
        "last_analyzed",
    ]
    df_to_db = df_pred[cols]

    with app.app_context():
        with db.engine.connect() as conn:
            df_to_db.to_sql(
                name="predictions",
                con=conn,
                if_exists="append",
                index=False,
            )
            conn.commit()
    print(f"Lưu thành công {len(df_to_db)} bản ghi dự đoán vào bảng 'predictions'!")


if __name__ == "__main__":
    df_clean = load_data()
    df_features = extract_customer_features(df_clean)
    display_cols = ['customer_code', 'customer_name'] + FEATURES
    print("BẢNG 7 ĐẶC TRƯNG KHÁCH HÀNG):")
    print(df_features[display_cols].head(20).to_string(index=False))
    df_labeled = create_churn_labels(df_features)

    total_customers = len(df_labeled)
    churn_count = df_labeled["churn"].sum()
    loyal_count = total_customers - churn_count
    churn_percentage = df_labeled["churn"].mean() * 100
    loyal_percentage = 100 - churn_percentage

    model = train_churn_model(df_labeled)
    save_predictions_to_db(df_features, model)