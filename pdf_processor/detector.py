"""PDF page type detection: native, scanned, or mixed (CJK-aware)."""

import fitz

from config import CONFIG
from utils.helpers import count_cjk_chars


class PDFDetector:
    """Classify each page of a PDF as native, scanned, or mixed."""

    def classify_page(self, page: fitz.Page) -> str:
        """Classify a single page. Returns: 'native', 'scanned', or 'mixed'."""
        text = page.get_text("text") or ""
        char_count = len(text.strip())
        cjk_count = count_cjk_chars(text)

        # Check for images
        images = page.get_images(full=True)
        page_area = page.rect.width * page.rect.height

        total_image_area = 0.0
        for img in images:
            try:
                xref = img[0]
                img_rects = page.get_image_rects(xref)
                for rect in img_rects:
                    total_image_area += rect.width * rect.height
            except Exception:
                continue

        image_area_ratio = total_image_area / page_area if page_area > 0 else 0

        # CJK-aware classification: 30 CJK chars is enough to be "native"
        has_enough_text = (char_count >= CONFIG.native_text_min_chars or
                          cjk_count >= CONFIG.native_cjk_min_chars)
        has_dominant_image = image_area_ratio >= CONFIG.scanned_image_area_ratio

        if has_enough_text and not has_dominant_image:
            return "native"
        elif not has_enough_text and has_dominant_image:
            return "scanned"
        elif has_enough_text and has_dominant_image:
            return "mixed"
        else:
            if char_count < 10 and cjk_count < 5:
                return "scanned"
            return "native"

    def classify_document(self, doc: fitz.Document) -> list[str]:
        """Classify all pages in a document."""
        return [self.classify_page(doc[i]) for i in range(len(doc))]
