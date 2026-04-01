"""PDF page type detection: native, scanned, or mixed."""

import fitz

from config import CONFIG


class PDFDetector:
    """Classify each page of a PDF as native, scanned, or mixed."""

    def classify_page(self, page: fitz.Page) -> str:
        """Classify a single page.

        Returns: 'native', 'scanned', or 'mixed'
        """
        # Extract text character count
        text = page.get_text("text") or ""
        char_count = len(text.strip())

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

        # Classification logic
        has_enough_text = char_count >= CONFIG.native_text_min_chars
        has_dominant_image = image_area_ratio >= CONFIG.scanned_image_area_ratio

        if has_enough_text and not has_dominant_image:
            return "native"
        elif not has_enough_text and has_dominant_image:
            return "scanned"
        elif has_enough_text and has_dominant_image:
            return "mixed"
        else:
            # Very little text, no dominant image → likely blank or sparse
            if char_count < 10:
                return "scanned"  # treat as scanned to attempt OCR
            return "native"

    def classify_document(self, doc: fitz.Document) -> list[str]:
        """Classify all pages in a document."""
        return [self.classify_page(doc[i]) for i in range(len(doc))]
