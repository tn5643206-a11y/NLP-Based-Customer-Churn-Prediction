# Alt + Shift + E -> Chạy code theo đoạn
import re
import unicodedata
import numpy as np
import pandas as pd
import underthesea
import stopwordsiso
from sqlalchemy import text
from myapp import app, db

TEENCODE_DICT = {
    'ko': 'không', 'khong': 'không', 'k': 'không', 'kh': 'không',
    'sp': 'sản phẩm', 'đc': 'được', 'dc': 'được', 'dk': 'được',
    'bt': 'biết', 'vs': 'với', 'ms': 'mới', 'ntn': 'như thế nào',
    'lun': 'luôn', 'ok': 'tốt', 'okie': 'tốt', 'good': 'tốt', 'tot': 'tốt',
    'ship': 'giao hàng', 'date': 'hạn sử dụng', 'hsd': 'hạn sử dụng',
    'combo': 'gói', 'thanks': 'cảm ơn', 'tks': 'cảm ơn', 'you': 'bạn',
    'time': 'thời gian', 'dòn': 'giòn', 'ròn': 'giòn', 'ngòn': 'ngon',
    'hủ': 'hộp', 'hop': 'hợp', 'goi': 'gói', 'rat': 'rất', 'an': 'ăn',
    'hat': 'hạt', 'dep': 'đẹp', 'nua': 'nữa', 'tiep': 'tiếp', 'đăt': 'đặt',
    'minh': 'mình', 'nhìu': 'nhiều', 'nhiu': 'nhiều', 'nhiêu': 'nhiều',
    'lức': 'lứt', 'hiu': 'ỉu', 'luong': 'lượng', 'hihi': 'vui vẻ', 'ngón': 'ngon', 'hột': 'hạt'
}

NEGATION_WORDS = {'không', 'chưa', 'chẳng', 'chả', 'kém', 'ít'}

POSITIVE_WORDS = {
    'ngon', 'giòn', 'thơm', 'ngọt', 'béo', 'mềm', 'dẻo', 'đậm_đà',
    'ngon_miệng', 'vừa_vặn', 'vừa_phải', 'vừa', 'ghiền', 'tốt',
    'chất_lượng', 'chat_lượng', 'chuẩn', 'đẹp', 'sạch_sẽ', 'nhanh',
    'cẩn_thận', 'kỹ', 'kĩ', 'chắc_chắn', 'thân_thiện', 'hài_lòng',
    'thích', 'tuyệt_vời', 'tuyệt', 'đầy_đủ', 'đủ', 'hợp_lý',
    'phù_hợp', 'hợp', 'rẻ', 'được_giá', 'đáng', 'ủng_hộ', 'ổn',
    'tạm', 'rõ_ràng', 'đặc_biệt', 'hy_vọng', 'cảm_ơn', 'đúng'
}

NEGATIVE_WORDS = {
    'khét', 'cháy', 'đắng', 'tanh', 'ỉu', 'cũ', 'chua_chua', 'nhạt',
    'thất_vọng', 'dở_tệ', 'chán', 'sai', 'ẩu', 'nhám'
}

def _init_stopwords() -> set:
    raw_stopwords = set(stopwordsiso.stopwords("vi"))
    formatted = {w.strip().replace(" ", "_") for w in raw_stopwords if w.strip()}
    keep_words = NEGATION_WORDS | POSITIVE_WORDS | NEGATIVE_WORDS
    formatted = formatted - keep_words

    extra_stopwords = {
        'ạ', 'à', 'nè', 'nha', 'nhé', 'nghen', 'mình', 'bạn', 'shop', 'tiki',
        'sản_phẩm', 'hàng', 'được', 'có', 'và', 'là', 'thì', 'mà', 'của', 'ở',
        'cho', 'với', 'vì', 'do', 'các', 'cũng', 'đã', 'sẽ', 'rồi', 'này'
    }
    return formatted | extra_stopwords

STOPWORDS_SET = _init_stopwords()

def filter_spam_outliers(df: pd.DataFrame, text_col: str = 'comment_text',
                               iqr_multiplier: float = 1.5) -> pd.DataFrame:
    df_clean = df.dropna(subset=[text_col]).copy()
    df_clean = df_clean[df_clean[text_col].astype(str).str.strip() != ''].reset_index(drop=True)

    word_counts = df_clean[text_col].apply(lambda x: len(str(x).split()))
    q1 = word_counts.quantile(0.25)
    q3 = word_counts.quantile(0.75)
    upper_limit = q3 + iqr_multiplier * (q3 - q1)

    def _is_valid(text):
        text_str = str(text).lower()
        if bool(re.search(r'http\S+|www\S+|https\S+', text_str)):
            return False
        if len(text_str.split()) > upper_limit:
            return False
        return True

    valid_mask = df_clean[text_col].apply(_is_valid)
    return df_clean[valid_mask].reset_index(drop=True)

def clean_characters(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFC', text).lower()
    text = re.sub(r'\d+', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'(\w)\1{2,}', r'\1', text)
    return re.sub(r'\s+', ' ', text).strip()

def normalize_teencode(text: str) -> str:
    if not text:
        return ""
    words = text.split()
    return " ".join([TEENCODE_DICT.get(w, w) for w in words])


def tokenize_and_negate(text: str) -> str:
    if not text:
        return ""
    tokens = underthesea.word_tokenize(text, format="text").split()
    new_tokens = []
    skip_next = False
    n = len(tokens)

    for i in range(n):
        if skip_next:
            skip_next = False
            continue

        current_token = tokens[i]
        if current_token in NEGATION_WORDS and i + 1 < n:
            next_token = tokens[i + 1]
            if next_token in POSITIVE_WORDS:
                new_tokens.append("noPositive")
                skip_next = True
                continue
            elif next_token in NEGATIVE_WORDS:
                new_tokens.append("noNegative")
                skip_next = True
                continue

        new_tokens.append(current_token)

    return " ".join(new_tokens)

def remove_stopwords(text: str) -> str:
    if not text:
        return ""
    tokens = text.split()
    clean_tokens = [
        w for w in tokens
        if w.startswith("no_") or w in {"noPositive", "noNegative"} or (w not in STOPWORDS_SET)
    ]
    return " ".join(clean_tokens)

def clean_whitespaces(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def preprocess_comment(text: str) -> str:
    text = clean_characters(text)
    text = normalize_teencode(text)
    text = tokenize_and_negate(text)
    text = remove_stopwords(text)
    text = clean_whitespaces(text)
    return text

def run_nlp_pipeline_from_db():
    with app.app_context():
        print("Đang tải dữ liệu từ bảng [reviews] trong SQL Server")

        query = """
        SELECT 
            id,
            product_id,
            customer_id,
            rating_stars,
            comment_text
        FROM reviews 
        WHERE comment_text IS NOT NULL
        AND sentiment IS NULL
    """
        df_raw = pd.read_sql(query, con=db.engine)
        if df_raw.empty:
            print("Không có đánh giá mới cần phân tích.")
            return pd.DataFrame()
        print(f"Đã tải thành công {len(df_raw)} bản ghi mới từ CSDL.")

        df = filter_spam_outliers(df_raw, text_col='comment_text')
        print(f"Sau bước lọc thô còn lại {len(df)} bản ghi hợp lệ.")

        print("Đang thực hiện bước làm sạch ký tự, teencode, tách từ, stopwords)")
        df['clean_comment'] = df['comment_text'].apply(preprocess_comment)

        df['clean_comment'] = df['clean_comment'].replace('', np.nan)
        df_cleaned = df.dropna(subset=['clean_comment']).reset_index(drop=True)

        print(f"Xong bước tiền xử lý! Tổng số bản ghi sạch sẵn sàng: {len(df_cleaned)}")
        return df_cleaned

def classify_sentiment(df: pd.DataFrame) -> pd.DataFrame:
    def _get_sentiment(row):
        rating = row.get('rating_stars')
        clean_text = row.get('clean_comment').lower()
        tokens = set(clean_text.split())

        if pd.notnull(rating) and rating >= 4:
            return  'Positive'
        if pd.notnull(rating) and rating <= 3:
            return  'Negative'
        if 'noPositive' in tokens:
            return 'Negative'
        if 'noNegative' in tokens:
            return 'Positive'
        return 'Positive'

    df['sentiment'] = df.apply(_get_sentiment, axis=1)
    return df


def extract_aspect_rules(df_input: pd.DataFrame) -> pd.DataFrame:
    df = df_input.copy()

    df['cluster_id'] = 4
    df['cluster_name'] = "Hài lòng / Không có khiếu nại"

    df['aspect_shipping'] = 0  # Cụm 0
    df['aspect_quality'] = 0  # Cụm 1
    df['aspect_taste'] = 0  # Cụm 2
    df['aspect_packaging'] = 0  # Cụm 3

    for idx, row in df.iterrows():
        if row['sentiment'] == 'Negative':
            t = " " + str(row['clean_comment']).lower() + " "

            if any(w in t for w in [
                'cân điêu', 'ăn_gian', 'vỏ hộp', 'hộp đựng', 'nặng gr', 'kể_cả hộp',
                'bán cân', 'quảng_cáo g', 'hộp g', 'khối_lượng', 'dán thêm mác',
                'ngắn tủn', 'g hộp hộp', 'bán vỏ hộp', 'nắp hộp bung'
            ]):
                df.at[idx, 'cluster_id'] = 3
                df.at[idx, 'cluster_name'] = "Quy cách đóng gói & định lượng"
                df.at[idx, 'aspect_packaging'] = 1

            elif any(w in t for w in [
                'mốc', 'đắng', 'hôi_dầu', 'hôi', 'hư', 'lép', 'sâu', 'cháy',
                'khét', 'gắt_dầu', 'gắt dầu', 'đen thui', 'mọt', 'hột bỏ', 'dở_tệ',
                'cứng_ngắt', 'đen mốc', 'muồi dầu', 'tóc bao', 'mùi ghê', 'hôi dầu'
            ]):
                df.at[idx, 'cluster_id'] = 1
                df.at[idx, 'cluster_name'] = "Khuyết tật chất lượng Sản phẩm"
                df.at[idx, 'aspect_quality'] = 1

            elif any(w in t for w in [
                'giao sai', 'sai đơn', 'sai gói', 'giao thiếu', 'thiếu hạt', 'giao_nhầm',
                'giao chậm', 'hẹn giao', 'now_phí', 'shipper', 'vận_chuyển', 'chuyển đơn',
                'đặt vị', 'chậm', 'giao_hũ', 'đổi', 'sai sl', 'đóng_gói ẩu', 'gói ẩu',
                'vỡ hộp', 'ma_nát', 'giao hang', 'giao nopositive', 'loại vỏ giao',
                'giao khách_hàng bóc vỏ', 'giao trễ', 'giao hư', 'giao đúng', 'giao toàn hư',
                'treo đầu dê'
            ]):
                df.at[idx, 'cluster_id'] = 0
                df.at[idx, 'cluster_name'] = "Sự cố giao hàng & phân loại đơn"
                df.at[idx, 'aspect_shipping'] = 1

            else:
                df.at[idx, 'cluster_id'] = 2
                df.at[idx, 'cluster_name'] = "Cảm quan hương vị & trải nghiệm chung"
                df.at[idx, 'aspect_taste'] = 1

    def assign_processing_status(row):
        if row.get('sentiment') == 'Negative' or (pd.notna(row.get('cluster_name')) and
                                                  row.get('cluster_name') != 'Hài lòng / Không có khiếu nại'):
            return 'pending'
        return None
    df['processing_status'] = df.apply(assign_processing_status, axis=1)

    return df

def update_results_to_db(df: pd.DataFrame):
    print("Cập nhật kết quả phân tích bình luận [reviews] trong cơ sở dữ liệu")
    update_data = []

    for _, row in df.iterrows():
        raw_status = row.get('processing_status')
        if pd.isna(raw_status) or str(raw_status).strip().lower() in ['nan', 'none', '']:
            status_val = None
        else:
            status_val = str(raw_status).strip().upper()
        update_data.append({
            'review_id': int(row['id']),
            'sentiment': str(row['sentiment']),
            'cluster_id': int(row['cluster_id']),
            'cluster_name': str(row['cluster_name']),
            'processing_status': status_val
        })
    update_sql = text("""
        UPDATE reviews
        SET sentiment = :sentiment,
            cluster_id = :cluster_id,
            cluster_name = :cluster_name,
            processing_status = :processing_status
        WHERE id = :review_id
    """)

    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(update_sql, update_data)
    print(f"Cập nhật thành công {len(update_data)} dòng vào bảng [reviews]!")

if __name__ == "__main__":
    df_result = run_nlp_pipeline_from_db()
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.width', 500)
    print("\n10 dòng kết quả mãu sau khi xử lý từ CSDL")
    print(df_result[['id', 'rating_stars', 'comment_text', 'clean_comment']].head(10))
    df_result = classify_sentiment(df_result)
    df_result = extract_aspect_rules(df_result)
    df_result = update_results_to_db(df_result)





