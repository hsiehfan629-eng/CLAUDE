"""Centralized configuration for the Revenue Detail Testing application."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class AppConfig:
    # --- Language / i18n ---
    language: str = "zh"

    # --- PDF Processing ---
    max_file_size_mb: int = 200
    pdf_batch_size: int = 10
    image_dpi: int = 300

    # --- OCR ---
    ocr_language: str = "chi_sim+eng"
    tesseract_config: str = "--oem 3 --psm 6"
    tesseract_psm_fallbacks: list[int] = field(default_factory=lambda: [6, 3, 11])
    confidence_threshold: float = 0.60
    ocr_retry_threshold: float = 0.50  # retry with different PSM if below this
    ocr_timeout_seconds: int = 60

    # --- Text Detection Thresholds ---
    native_text_min_chars: int = 50
    native_cjk_min_chars: int = 30  # CJK-aware: 30 Chinese chars is sufficient
    scanned_image_area_ratio: float = 0.30

    # --- Table Extraction ---
    table_snap_tolerance: int = 3
    table_join_tolerance: int = 3

    # --- Preprocessing ---
    preprocessing_grayscale: bool = True
    preprocessing_denoise: bool = True
    preprocessing_denoise_h: int = 7  # tuned for Chinese (lower = preserve fine strokes)
    preprocessing_clahe: bool = True
    preprocessing_clahe_clip: float = 3.0  # increased for scanned docs
    preprocessing_binarize: bool = True
    preprocessing_deskew: bool = True
    preprocessing_deskew_max_angle: float = 15.0
    preprocessing_morphological_close: bool = True  # connect broken Chinese strokes

    # --- Revenue Audit ---
    amount_tolerance: Decimal = Decimal("1.00")  # ±1 yuan for check ③
    price_tolerance: Decimal = Decimal("0.01")  # ±0.01 for price comparison
    tax_rate: Decimal = Decimal("1.13")
    fuzzy_match_threshold: float = 0.80  # for customer/product name matching
    file_match_threshold: float = 0.70  # for PDF-to-group matching

    # --- Document classification keywords ---
    contract_keywords: list[str] = field(default_factory=lambda: [
        "合同", "订单", "采购", "销售",
    ])
    receipt_keywords: list[str] = field(default_factory=lambda: [
        "回签联", "送货单", "出库单", "签收",
    ])
    reconciliation_keywords: list[str] = field(default_factory=lambda: [
        "对账单",
    ])
    authorization_keywords: list[str] = field(default_factory=lambda: [
        "授权书", "授权",
    ])

    # --- Supported date formats (cross-platform compatible) ---
    supported_date_formats: list[str] = field(default_factory=lambda: [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%y-%m-%d",
    ])

    # --- Amount regex ---
    amount_pattern: str = (
        r"[(\uff08]?\s*"
        r"(?:[\$\u00a5\uffe5]|CNY|RMB|USD)?\s*"
        r"[\-\uff0d]?\s*"
        r"\d{1,3}(?:[,\uff0c]\d{3})*(?:[.\uff0e]\d{1,4})?"
        r"\s*[)\uff09]?"
    )


# Excel column mapping
EXCEL_COLS = {
    "year": "A",
    "month": "B",
    "customer": "C",
    "product_category": "D",
    "order_date": "E",
    "order_no": "F",
    "material_name": "G",
    "spec_model": "H",
    "delivery_no": "I",
    "delivery_date": "J",
    "material_code": "K",
    "delivery_qty": "L",
    "unit_price": "M",
    "revenue_tax": "N",
    "confirm_date": "O",
    "voucher_no": "P",
    "revenue_notax": "Q",
    "logistics_company": "R",
    "logistics_no": "S",
    "logistics_sign_date": "T",
    "customer_sign_date": "U",
    "signer": "V",
    "check1": "W",
    "check2": "X",
    "check3": "Y",
    "check4": "Z",
    "check5": "AA",
    "attachment_index": "AB",
    "attachment_result": "AC",
}


# Bilingual text dictionary
_TEXTS = {
    "app_title": {"zh": "收入细节测试核查系统", "en": "Revenue Detail Testing System"},
    "upload_excel": {"zh": "上传Excel细节测试样本", "en": "Upload Excel Detail Test Sample"},
    "upload_folder": {"zh": "上传佐证文件（PDF）", "en": "Upload Supporting Documents (PDF)"},
    "start_processing": {"zh": "开始处理", "en": "Start Processing"},
    "processing": {"zh": "正在处理...", "en": "Processing..."},
    "run_test": {"zh": "执行五项核查", "en": "Run 5 Verifications"},
    "export_report": {"zh": "导出核查结果", "en": "Export Results"},
    "download_excel": {"zh": "下载已填写的Excel", "en": "Download Completed Excel"},
    "summary": {"zh": "核查汇总", "en": "Summary"},
    "detail": {"zh": "核查明细", "en": "Detail"},
    "language_switch": {"zh": "English", "en": "中文"},
    "sidebar_title": {"zh": "控制面板", "en": "Control Panel"},
    "step1": {"zh": "步骤1: 上传Excel样本", "en": "Step 1: Upload Excel Sample"},
    "step2": {"zh": "步骤2: 上传佐证文件", "en": "Step 2: Upload Documents"},
    "step3": {"zh": "步骤3: 执行核查", "en": "Step 3: Run Verification"},
    "step4": {"zh": "步骤4: 查看结果并导出", "en": "Step 4: Review & Export"},
    "check1": {"zh": "①系统信息与合同/订单一致性", "en": "①System vs Contract Consistency"},
    "check2": {"zh": "②出库单信息一致性", "en": "②Delivery Note Consistency"},
    "check3": {"zh": "③收入确认金额准确性", "en": "③Revenue Amount Accuracy"},
    "check4": {"zh": "④收入确认时点合规性", "en": "④Revenue Timing Compliance"},
    "check5": {"zh": "⑤签收人员授权验证", "en": "⑤Signer Authorization"},
    "matched": {"zh": "已匹配", "en": "Matched"},
    "unmatched": {"zh": "未匹配", "en": "Unmatched"},
}


def t(key: str, lang: str = "zh") -> str:
    """Get bilingual text by key."""
    entry = _TEXTS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("zh", key))


CONFIG = AppConfig()
