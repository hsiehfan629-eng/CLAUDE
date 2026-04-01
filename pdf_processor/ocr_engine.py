"""OCR engine for scanned PDF pages using pytesseract."""

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

try:
    from pdf2image import convert_from_bytes
except ImportError:
    convert_from_bytes = None


class OCREngine:
    """Tesseract OCR wrapper with Chinese language support."""

    def __init__(self):
        self.preprocessor = ImagePreprocessor()

    def ocr_page(self, page: fitz.Page, page_number: int) -> tuple[str, list, float]:
        """OCR a single page.

        Returns: (full_text, list_of_TextBlocks, average_confidence)
        """
        from audit.models import TextBlock

        if pytesseract is None:
            return "", [], 0.0

        # Convert page to image
        image = self._page_to_image(page)
        if image is None:
            return "", [], 0.0

        # Convert PIL Image to numpy array
        img_array = np.array(image)

        # Preprocess
        processed = self.preprocessor.preprocess(img_array)

        # Run OCR with word-level data
        try:
            data = pytesseract.image_to_data(
                Image.fromarray(processed) if len(processed.shape) == 2 else image,
                lang=CONFIG.ocr_language,
                config=CONFIG.tesseract_config,
                output_type=pytesseract.Output.DICT,
            )
        except Exception:
            # Fallback to simple string extraction
            try:
                text = pytesseract.image_to_string(
                    Image.fromarray(processed) if len(processed.shape) == 2 else image,
                    lang=CONFIG.ocr_language,
                    config=CONFIG.tesseract_config,
                )
                return text, [TextBlock(
                    page_number=page_number,
                    content=text,
                    bbox=(0, 0, page.rect.width, page.rect.height),
                    confidence=0.5,
                    block_type="paragraph",
                )], 0.5
            except Exception:
                return "", [], 0.0

        # Parse results
        full_text_parts = []
        blocks = []
        confidences = []
        page_w, page_h = page.rect.width, page.rect.height
        img_w, img_h = image.size

        n_boxes = len(data.get("text", []))
        current_block_text = []
        current_block_confs = []

        for i in range(n_boxes):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])

            if not text:
                # End of a block, save accumulated text
                if current_block_text:
                    block_text = " ".join(current_block_text)
                    avg_conf = (sum(current_block_confs) / len(current_block_confs) / 100.0
                                if current_block_confs else 0.0)
                    full_text_parts.append(block_text)
                    blocks.append(TextBlock(
                        page_number=page_number,
                        content=block_text,
                        bbox=(0, 0, page_w, page_h),
                        confidence=max(0.0, min(1.0, avg_conf)),
                        block_type="paragraph",
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
            avg_conf = (sum(current_block_confs) / len(current_block_confs) / 100.0
                        if current_block_confs else 0.0)
            full_text_parts.append(block_text)
            blocks.append(TextBlock(
                page_number=page_number,
                content=block_text,
                bbox=(0, 0, page_w, page_h),
                confidence=max(0.0, min(1.0, avg_conf)),
                block_type="paragraph",
            ))

        full_text = "\n".join(full_text_parts)
        avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0

        return full_text, blocks, avg_confidence

    def _page_to_image(self, page: fitz.Page) -> Image.Image | None:
        """Convert a fitz page to PIL Image."""
        try:
            # Use PyMuPDF's built-in rendering
            mat = fitz.Matrix(CONFIG.image_dpi / 72, CONFIG.image_dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            return Image.open(io.BytesIO(img_data))
        except Exception:
            return None
