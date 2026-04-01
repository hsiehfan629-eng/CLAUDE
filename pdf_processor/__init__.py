"""PDF Processing Pipeline - facade module."""

from .detector import PDFDetector
from .text_extractor import TextExtractor
from .table_extractor import TableExtractor
from .ocr_engine import OCREngine
from .preprocessor import ImagePreprocessor

__all__ = [
    "PDFDetector",
    "TextExtractor",
    "TableExtractor",
    "OCREngine",
    "ImagePreprocessor",
    "process_pdf",
]


def process_pdf(file_path: str | None = None, file_bytes: bytes | None = None,
                file_name: str = "unknown.pdf") -> "ProcessedDocument":
    """Process a PDF file through the full extraction pipeline.

    Args:
        file_path: Path to PDF file on disk.
        file_bytes: Raw PDF bytes (for uploaded files).
        file_name: Original file name for reporting.

    Returns:
        ProcessedDocument with all extracted data.
    """
    import fitz
    import time
    from audit.models import ProcessedDocument, ExtractedTable, TextBlock

    start_time = time.time()
    warnings = []
    page_types = []
    all_text_blocks: list[TextBlock] = []
    all_tables: list[ExtractedTable] = []
    raw_text_by_page: dict[int, str] = {}

    # Open PDF
    try:
        if file_bytes:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        elif file_path:
            doc = fitz.open(file_path)
        else:
            raise ValueError("Either file_path or file_bytes must be provided")
    except Exception as e:
        return ProcessedDocument(
            file_name=file_name,
            total_pages=0,
            page_types=[],
            text_blocks=[],
            extracted_tables=[],
            raw_text_by_page={},
            processing_time=time.time() - start_time,
            warnings=[f"Failed to open PDF: {e}"],
        )

    detector = PDFDetector()
    text_extractor = TextExtractor()
    ocr_engine = OCREngine()
    table_extractor = TableExtractor()

    total_pages = len(doc)

    for page_num in range(total_pages):
        try:
            page = doc[page_num]

            # Step 1: Detect page type
            page_type = detector.classify_page(page)
            page_types.append(page_type)

            # Step 2: Extract text based on type
            if page_type in ("native", "mixed"):
                blocks = text_extractor.extract_page_blocks(page, page_num + 1)
                all_text_blocks.extend(blocks)
                raw_text = text_extractor.extract_page_text(page)
                raw_text_by_page[page_num + 1] = raw_text

            if page_type in ("scanned", "mixed"):
                ocr_text, ocr_blocks, avg_conf = ocr_engine.ocr_page(page, page_num + 1)
                if page_type == "scanned":
                    raw_text_by_page[page_num + 1] = ocr_text
                    all_text_blocks.extend(ocr_blocks)
                elif page_type == "mixed" and not raw_text_by_page.get(page_num + 1):
                    raw_text_by_page[page_num + 1] = ocr_text
                    all_text_blocks.extend(ocr_blocks)

                if avg_conf < 0.4:
                    warnings.append(
                        f"Page {page_num + 1}: Low OCR confidence ({avg_conf:.0%}), "
                        f"manual review recommended"
                    )

            # Step 3: Extract tables
            page_tables = table_extractor.extract_tables(page, page_num + 1, page_type)
            all_tables.extend(page_tables)

        except Exception as e:
            page_types.append("error")
            warnings.append(f"Page {page_num + 1}: Processing error - {e}")

    doc.close()

    return ProcessedDocument(
        file_name=file_name,
        total_pages=total_pages,
        page_types=page_types,
        text_blocks=all_text_blocks,
        extracted_tables=all_tables,
        raw_text_by_page=raw_text_by_page,
        processing_time=time.time() - start_time,
        warnings=warnings,
    )
