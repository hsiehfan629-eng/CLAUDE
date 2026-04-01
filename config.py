"""Centralized configuration for the Revenue Detail Testing application."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class AppConfig:
    # --- Language / i18n ---
    language: str = "zh"  # "zh" or "en"

    # --- PDF Processing ---
    max_file_size_mb: int = 200
    pdf_batch_size: int = 10
    image_dpi: int = 300

    # --- OCR ---
    ocr_language: str = "chi_sim+eng"
    tesseract_config: str = "--oem 3 --psm 6"
    confidence_threshold: float = 0.60
    ocr_retry_threshold: float = 0.40
    ocr_timeout_seconds: int = 60

    # --- Text Detection Thresholds ---
    native_text_min_chars: int = 50
    scanned_image_area_ratio: float = 0.30

    # --- Table Extraction ---
    table_snap_tolerance: int = 3
    table_join_tolerance: int = 3

    # --- Preprocessing toggles ---
    preprocessing_grayscale: bool = True
    preprocessing_denoise: bool = True
    preprocessing_clahe: bool = True
    preprocessing_binarize: bool = True
    preprocessing_deskew: bool = True

    # --- Revenue Audit Specific ---
    amount_tolerance: Decimal = Decimal("1.00")  # ±1 yuan for check ③
    tax_rate: Decimal = Decimal("1.13")  # VAT rate for check ③

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

    # --- Supported date formats ---
    supported_date_formats: list[str] = field(default_factory=lambda: [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y.%m.%d",
        "%Y年%m月%d日",
        "%Y年%-m月%-d日",
        "%d-%m-%Y",
        "%Y%m%d",
    ])

    # --- Amount regex ---
    amount_pattern: str = (
        r"[(\uff08]?\s*"
        r"(?:[\$\u00a5\uffe5]|CNY|RMB|USD)?\s*"
        r"-?\s*"
        r"\d{1,3}(?:[,\uff0c]\d{3})*(?:[.\uff0e]\d{1,4})?"
        r"\s*[)\uff09]?"
    )


# Excel column mapping (0-indexed) for the revenue detail testing template
# Row 2 = headers, data starts row 3
EXCEL_COLS = {
    "year": "A",           # 年度
    "month": "B",          # 月份
    "customer": "C",       # 客户名称
    "product_category": "D",  # 产品类别
    "order_date": "E",     # 订单日期
    "order_no": "F",       # 订单编号
    "material_name": "G",  # 物料名称
    "spec_model": "H",     # 规格型号
    "delivery_no": "I",    # 出库单号 ★关键匹配字段
    "delivery_date": "J",  # 出库日期
    "material_code": "K",  # 物料代码
    "delivery_qty": "L",   # 出库数量
    "unit_price": "M",     # 产品单价
    "revenue_tax": "N",    # 含税收入
    "confirm_date": "O",   # 收入确认日期
    "voucher_no": "P",     # 凭证号
    "revenue_notax": "Q",  # 不含税收入
    "logistics_company": "R",  # 物流公司 ★待填写
    "logistics_no": "S",      # 物流单号 ★待填写
    "logistics_sign_date": "T",  # 签收日期 ★留空不填
    "customer_sign_date": "U",   # 客户签收日期 ★待填写
    "signer": "V",                # 签收人员 ★待填写
    "check1": "W",  # ① 系统信息与合同一致性
    "check2": "X",  # ② 出库单信息一致性
    "check3": "Y",  # ③ 收入确认金额准确性
    "check4": "Z",  # ④ 收入确认时点合规性
    "check5": "AA", # ⑤ 签收人员授权验证
    "attachment_index": "AB",  # 附件索引号
    "attachment_result": "AC", # 附件检查结果
}


# Bilingual text dictionary
_TEXTS = {
    "app_title": {"zh": "收入细节测试核查系统", "en": "Revenue Detail Testing System"},
    "upload_excel": {"zh": "上传Excel细节测试样本", "en": "Upload Excel Detail Test Sample"},
    "upload_folder": {"zh": "上传佐证文件（PDF）", "en": "Upload Supporting Documents (PDF)"},
    "start_processing": {"zh": "开始核查", "en": "Start Verification"},
    "processing": {"zh": "正在处理...", "en": "Processing..."},
    "extraction_results": {"zh": "提取结果", "en": "Extraction Results"},
    "run_test": {"zh": "执行五项核查", "en": "Run 5 Verifications"},
    "findings": {"zh": "核查结果", "en": "Verification Results"},
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
    "pass_all": {"zh": "全部通过", "en": "All Passed"},
    "delivery_no": {"zh": "出库单号", "en": "Delivery Note No."},
    "customer": {"zh": "客户名称", "en": "Customer Name"},
    "contract": {"zh": "合同/订单", "en": "Contract/Order"},
    "receipt": {"zh": "回签联/送货单", "en": "Delivery Receipt"},
    "reconciliation": {"zh": "对账单", "en": "Reconciliation"},
    "authorization": {"zh": "授权书", "en": "Authorization Letter"},
    "missing_contract": {"zh": "缺合同", "en": "Missing Contract"},
    "missing_receipt": {"zh": "缺回签联", "en": "Missing Receipt"},
    "missing_auth": {"zh": "未提供授权书", "en": "No Authorization"},
    "match_status": {"zh": "匹配状态", "en": "Match Status"},
    "matched": {"zh": "已匹配", "en": "Matched"},
    "unmatched": {"zh": "未匹配", "en": "Unmatched"},
    "total_groups": {"zh": "出库单号总数", "en": "Total Delivery Notes"},
    "total_checked": {"zh": "已核查", "en": "Checked"},
    "total_passed": {"zh": "全部通过", "en": "All Passed"},
    "total_exceptions": {"zh": "存在异常", "en": "Exceptions"},
}


def t(key: str, lang: str = "zh") -> str:
    """Get bilingual text by key."""
    entry = _TEXTS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("zh", key))


# Global config instance
CONFIG = AppConfig()
