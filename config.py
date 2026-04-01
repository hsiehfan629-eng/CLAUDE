"""Centralized configuration for the Audit Detail Testing application."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class AppConfig:
    # --- Language / i18n ---
    language: str = "zh"  # "zh" or "en"

    # --- PDF Processing ---
    max_file_size_mb: int = 200
    pdf_batch_size: int = 10  # pages per batch for memory control
    image_dpi: int = 300  # DPI for scanned page conversion

    # --- OCR ---
    ocr_language: str = "chi_sim+eng"
    tesseract_config: str = "--oem 3 --psm 6"
    confidence_threshold: float = 0.60  # below this → flag for manual review
    ocr_retry_threshold: float = 0.40  # below this → retry with aggressive preprocessing
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

    # --- Audit ---
    default_amount_tolerance: Decimal = Decimal("0.01")
    default_amount_tolerance_pct: Decimal = Decimal("0.01")  # 1%
    default_date_tolerance_days: int = 3
    materiality_threshold: Decimal = Decimal("1000.00")

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

    # --- Amount regex (handles ¥, $, CNY, RMB, parentheses for negatives) ---
    amount_pattern: str = (
        r"[(\uff08]?\s*"
        r"(?:[\$\u00a5\uffe5]|CNY|RMB|USD)?\s*"
        r"-?\s*"
        r"\d{1,3}(?:[,\uff0c]\d{3})*(?:[.\uff0e]\d{1,4})?"
        r"\s*[)\uff09]?"
    )


# Bilingual text dictionary
_TEXTS = {
    "app_title": {"zh": "审计细节测试系统", "en": "Audit Detail Testing System"},
    "upload_excel": {"zh": "上传Excel抽样样本", "en": "Upload Excel Sampling Template"},
    "upload_folder": {"zh": "上传PDF文件夹", "en": "Upload PDF Folder"},
    "start_processing": {"zh": "开始处理", "en": "Start Processing"},
    "processing": {"zh": "正在处理...", "en": "Processing..."},
    "extraction_results": {"zh": "提取结果", "en": "Extraction Results"},
    "test_config": {"zh": "测试配置", "en": "Test Configuration"},
    "run_test": {"zh": "运行测试", "en": "Run Test"},
    "findings": {"zh": "审计发现", "en": "Audit Findings"},
    "export_report": {"zh": "导出报告", "en": "Export Report"},
    "page": {"zh": "页", "en": "Page"},
    "file_name": {"zh": "文件名", "en": "File Name"},
    "status": {"zh": "状态", "en": "Status"},
    "confidence": {"zh": "置信度", "en": "Confidence"},
    "severity_high": {"zh": "高", "en": "High"},
    "severity_medium": {"zh": "中", "en": "Medium"},
    "severity_low": {"zh": "低", "en": "Low"},
    "pass": {"zh": "通过", "en": "Pass"},
    "fail": {"zh": "不通过", "en": "Fail"},
    "manual_review": {"zh": "需人工复核", "en": "Manual Review Required"},
    "vouching": {"zh": "凭证抽查", "en": "Vouching"},
    "tracing": {"zh": "追踪测试", "en": "Tracing"},
    "recalculation": {"zh": "重新计算", "en": "Recalculation"},
    "analytical": {"zh": "分析性程序", "en": "Analytical Procedures"},
    "total_tested": {"zh": "测试总数", "en": "Total Tested"},
    "exceptions": {"zh": "异常数", "en": "Exceptions"},
    "pass_rate": {"zh": "通过率", "en": "Pass Rate"},
    "amount": {"zh": "金额", "en": "Amount"},
    "date": {"zh": "日期", "en": "Date"},
    "description": {"zh": "摘要", "en": "Description"},
    "account_code": {"zh": "科目编码", "en": "Account Code"},
    "vendor": {"zh": "供应商/客户", "en": "Vendor/Customer"},
    "extracted_value": {"zh": "提取值", "en": "Extracted Value"},
    "expected_value": {"zh": "预期值", "en": "Expected Value"},
    "difference": {"zh": "差异", "en": "Difference"},
    "tolerance": {"zh": "容差", "en": "Tolerance"},
    "select_test_type": {"zh": "选择测试类型", "en": "Select Test Type"},
    "select_key_fields": {"zh": "选择匹配字段", "en": "Select Key Fields"},
    "column_mapping": {"zh": "字段映射", "en": "Column Mapping"},
    "pdf_column": {"zh": "PDF提取字段", "en": "PDF Extracted Field"},
    "excel_column": {"zh": "Excel样本字段", "en": "Excel Sample Field"},
    "native": {"zh": "原生PDF", "en": "Native PDF"},
    "scanned": {"zh": "扫描件", "en": "Scanned"},
    "mixed": {"zh": "混合", "en": "Mixed"},
    "warnings": {"zh": "警告", "en": "Warnings"},
    "no_files": {"zh": "未上传文件", "en": "No Files Uploaded"},
    "batch_progress": {"zh": "批量处理进度", "en": "Batch Processing Progress"},
    "download_excel": {"zh": "下载Excel报告", "en": "Download Excel Report"},
    "download_csv": {"zh": "下载CSV报告", "en": "Download CSV Report"},
    "summary": {"zh": "汇总", "en": "Summary"},
    "detail": {"zh": "明细", "en": "Detail"},
    "sample_id": {"zh": "样本编号", "en": "Sample ID"},
    "matched_pdf": {"zh": "匹配PDF文件", "en": "Matched PDF File"},
    "match_status": {"zh": "匹配状态", "en": "Match Status"},
    "language_switch": {"zh": "English", "en": "中文"},
    "sidebar_title": {"zh": "控制面板", "en": "Control Panel"},
    "step1": {"zh": "步骤1: 上传Excel抽样样本", "en": "Step 1: Upload Excel Sample"},
    "step2": {"zh": "步骤2: 上传PDF文件", "en": "Step 2: Upload PDF Files"},
    "step3": {"zh": "步骤3: 配置并运行测试", "en": "Step 3: Configure & Run Tests"},
    "step4": {"zh": "步骤4: 查看结果并导出", "en": "Step 4: Review & Export"},
}


def t(key: str, lang: str = "zh") -> str:
    """Get bilingual text by key."""
    entry = _TEXTS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("zh", key))


# Global config instance
CONFIG = AppConfig()
