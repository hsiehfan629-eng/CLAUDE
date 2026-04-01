"""OCR engine for scanned PDF pages using pytesseract with PSM fallback."""

import io

import numpy as np
import fitz
from PIL import Image

from config import CONFIG
from .preprocessor import ImagePreprocessor

try:
    import pytesseract
except ImportError:
    pytesseract = None


class OCREngine:
    """Tesseract OCR wrapper with Chinese support and PSM fallback."""

    def __init__(self):
        self.preprocessor = ImagePreprocessor()

    def ocr_page(self, page: fitz.Page, page_number: int) -> tuple[str, list, float]:
        """OCR a single page with automatic PSM fallback for better accuracy.

        Returns: (full_text, list_of_TextBlocks, average_confidence)
        """
        from audit.models import TextBlock

        if pytesseract is None:
            return "", [], 0.0

        image = self._page_to_image(page)
        if image is None:
            return "", [], 0.0

        img_array = np.array(image)
        processed = self.preprocessor.preprocess(img_array)
        pil_img = Image.fromarray(processed) if len(processed.shape) == 2 else image

        # Try PSM fallback strategy for best accuracy
        best_text = ""
        best_blocks = []
        best_conf = 0.0

        for psm in CONFIG.tesseract_psm_fallbacks:
            config_str = f"--oem 3 --psm {psm}"
            text, blocks, conf = self._run_ocr(pil_img, page, page_number, config_str)

            if conf > best_conf:
                best_text = text
                best_blocks = blocks
                best_conf = conf

            # Good enough, no need to try more
            if conf >= CONFIG.ocr_retry_threshold:
                break

        return best_text, best_blocks, best_conf

    def _run_ocr(self, image: Image.Image, page: fitz.Page, page_number: int,
                 config_str: str) -> tuple[str, list, float]:
        """Run OCR with a specific config and return results."""
        from audit.models import TextBlock

        try:
            data = pytesseract.image_to_data(
                image,
                lang=CONFIG.ocr_language,
                config=config_str,
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            # Fallback to simple string
            try:
                text = pytesseract.image_to_string(
                    image, lang=CONFIG.ocr_language, config=config_str,
                )
                return text, [TextBlock(
                    page_number=page_number, content=text,
                    bbox=(0, 0, page.rect.width, page.rect.height),
                    confidence=0.5, block_type="paragraph",
                )], 0.5
            except Exception:
                return "", [], 0.0

        # Parse word-level results
        full_text_parts = []
        blocks = []
        confidences = []
        page_w, page_h = page.rect.width, page.rect.height

        n_boxes = len(data.get("text", []))
        current_block_text = []
        current_block_confs = []

        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])

            if not text:
                if current_block_text:
                    block_text = " ".join(current_block_text)
                    avg_conf = sum(current_block_confs) / len(current_block_confs) if current_block_confs else 0.0
                    # Normalize: Tesseract outputs 0-100, we need 0.0-1.0
                    avg_conf = max(0.0, min(1.0, avg_conf / 100.0))
                    full_text_parts.append(block_text)
                    blocks.append(TextBlock(
                        page_number=page_number, content=block_text,
                        bbox=(0, 0, page_w, page_h),
                        confidence=avg_conf, block_type="paragraph",
                    ))
                    current_block_text = []
                    current_block_confs = []
                continue

            if conf > 0:
                current_block_text.append(text)
                current_block_confs.append(conf)
                confidences.append(conf)

        # Handle last block
        if current_block_text:
            block_text = " ".join(current_block_text)
            avg_conf = sum(current_block_confs) / len(current_block_confs) if current_block_confs else 0.0
            avg_conf = max(0.0, min(1.0, avg_conf / 100.0))
            full_text_parts.append(block_text)
            blocks.append(TextBlock(
                page_number=page_number, content=block_text,
                bbox=(0, 0, page_w, page_h),
                confidence=avg_conf, block_type="paragraph",
            ))

        full_text = "\n".join(full_text_parts)
        # Overall confidence: average of word confidences, normalized 0-1
        avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        avg_confidence = max(0.0, min(1.0, avg_confidence))

        return full_text, blocks, avg_confidence

    def _page_to_image(self, page: fitz.Page) -> Image.Image | None:
        """Convert a fitz page to PIL Image at configured DPI."""
        try:
            mat = fitz.Matrix(CONFIG.image_dpi / 72, CONFIG.image_dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            return Image.open(io.BytesIO(img_data))
        except Exception:
            return None
