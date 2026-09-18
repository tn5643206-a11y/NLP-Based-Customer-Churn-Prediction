import requests
import time
import random
from datetime import datetime
from tqdm import tqdm
from myapp import app, db
from myapp.models import Product, Customer, Review
import os
import joblib
from myapp.nlp_analytics import run_nlp_pipeline_from_db, classify_sentiment, extract_aspect_rules, update_results_to_db
from myapp.churn_prediction import load_data, extract_customer_features, save_predictions_to_db, CHURN_MODEL

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://tiki.vn/',
    'x-guest-token': 'siAgalF6wpfoXrLYmKN71u5WHykcJTU3'
}

def crawl_and_save_to_sql():
    with app.app_context():

        print("Quét danh sách Product ID của Shop")
        product_ids = []

        for i in range(1, 8):
            params_id = {'limit': '40', 'page': str(i)}
            try:
                res = requests.get('https://api.tiki.vn/v2/seller/stores/tan-loc-phat/products', headers=HEADERS,
                                   params=params_id, timeout=10)
                if res.status_code == 200:
                    data = res.json().get('data', [])
                    if not data:
                        break
                    for record in data:
                        p_id = record.get('id')
                        if p_id and p_id not in product_ids:
                            product_ids.append(p_id)
                    print(f"Trang {i}: Quét được {len(data)} sản phẩm.")
            except Exception as e:
                print(f"Lỗi kết nối khi quét trang {i}: {e}")

            time.sleep(random.uniform(2, 5))

        print(f"Tổng cộng thu thập được: {len(product_ids)} sản phẩm.\n")

        print("Cào thông tin chi tiết và bình luận")

        total_reviews = 0

        for pid in tqdm(product_ids, desc="Tiến độ cào dữ liệu"):
            try:
                res_info = requests.get(f'https://tiki.vn/api/v2/products/{pid}', headers=HEADERS,
                                    params={'platform': 'web'}, timeout=10)
                if res_info.status_code != 200:
                    continue

                json_info = res_info.json()
                p_code = str(json_info.get('id'))
                spid = str(json_info.get('current_seller', {}).get('product_id') or json_info.get('seller_product_id') or pid)
                quantity_data = json_info.get('quantity_sold')
                qty_sold = quantity_data.get('value', 0) if isinstance(quantity_data, dict) else 0

                product = Product.query.filter_by(product_code=p_code).first()
                if not product:
                    product = Product(
                        product_code=p_code,
                        name=json_info.get('name', 'Sản phẩm không tên'),
                        price=json_info.get('price', 0),
                        quantity_sold=qty_sold
                    )
                    db.session.add(product)
                    db.session.commit()

                params_comment = {
                    'product_id': str(pid),
                    'spid': str(spid),
                    'page': '1',
                    'limit': '20',
                    'sort': 'score|desc,id|desc,stars|all',
                    'include': 'comments,contribute_info,attribute_vote_summary'
                }
                res_comment = requests.get('https://tiki.vn/api/v2/reviews', headers=HEADERS,
                                           params=params_comment, timeout=10)

                if res_comment.status_code == 200:
                    reviews_list = res_comment.json().get('data', [])
                    if len(reviews_list) > 0:
                        print(f"-> Sản phẩm {pid}: tìm thấy {len(reviews_list)} đánh giá.")

                    for rev in reviews_list:
                        created_by = rev.get('created_by')or {}
                        c_code = str(created_by.get('id') or rev.get('customer_id') or '')
                        c_name = created_by.get('full_name') or rev.get('created_by_name') or 'Khách hàng ẩn danh'
                        c_name = c_name[:100]

                        customer = None
                        if c_code:
                            customer = Customer.query.filter_by(customer_code=c_code).first()
                        if not customer:
                            customer = Customer.query.filter_by(name=c_name).first()

                        if not customer:
                            customer = Customer(
                                customer_code=c_code if c_code else None,
                                name=c_name
                            )
                            db.session.add(customer)
                            db.session.commit()

                        comment = rev.get('content') or ''
                        rating = rev.get('rating', 5)
                        created_at_ts = rev.get('created_at')
                        rev_date = datetime.fromtimestamp(created_at_ts) if created_at_ts else datetime.now()

                        if comment and comment.strip():
                            existing_review = Review.query.filter_by(
                                product_id=product.id,
                                customer_id=customer.id,
                                comment_text=comment
                            ).first()

                            if not existing_review:
                                new_review = Review(
                                    product_id=product.id,
                                    customer_id=customer.id,
                                    rating_stars=rating,
                                    comment_text=comment,
                                    review_date=rev_date
                                )
                                db.session.add(new_review)
                                total_reviews += 1

                    db.session.commit()

            except Exception as e:
                db.session.rollback()
                continue

            time.sleep(random.uniform(2, 5))

        print(f"\nĐã lưu {len(product_ids)} sản phẩm và {total_reviews} bình luận vào CSDL.")

def run_full_pipeline(progress_callback=None):
    if progress_callback:
        progress_callback("Đang cào dữ liệu sản phẩm và bình luận từ cửa hàng Tấn Phát Lộc...")
    crawl_and_save_to_sql()

    if progress_callback:
        progress_callback("Đang làm sạch văn bản, phân loại cảm xúc và phân cụm khiếu nại (NLP)...")
    df_clean_nlp = run_nlp_pipeline_from_db()
    if not df_clean_nlp.empty:
        df_classified = classify_sentiment(df_clean_nlp)
        df_aspects = extract_aspect_rules(df_classified)
        update_results_to_db(df_aspects)
    else:
        print("Bỏ qua bước phân loại vì không có dữ liệu mới.")

    if progress_callback:
        progress_callback("Đang tính toán 7 đặc trưng hành vi và dự báo rủi ro rời bỏ...")
    if os.path.exists(CHURN_MODEL):
        model = joblib.load(CHURN_MODEL)
        df_raw_churn = load_data()
        df_features = extract_customer_features(df_raw_churn)
        save_predictions_to_db(df_features, model)
    else:
        print(f"Cảnh báo: Không tìm thấy file mô hình tại {CHURN_MODEL}")

    if progress_callback:
        progress_callback("Hoàn thành quy trình xử lý dữ liệu!")

if __name__ == "__main__":
    crawl_and_save_to_sql()