"""Native PDF text extraction using PyMuPDF."""

import fitz

from audit.models import TextBlock


class TextExtractor:
    """Extract text from native (non-scanned) PDF pages."""

    def extract_page_text(self, page: fitz.Page) -> str:
        """Extract plain text from a page."""
        return page.get_text("text") or ""

    def extract_page_blocks(self, page: fitz.Page, page_number: int) -> list[TextBlock]:
        """Extract text blocks with position and font metadata."""
        blocks = []
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        page_height = page.rect.height

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # type 0 = text block
                continue

            bbox = tuple(block["bbox"])
            block_text_parts = []

            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                if line_text.strip():
                    block_text_parts.append(line_text)

            content = "\n".join(block_text_parts)
            if not content.strip():
                continue

            # Determine block type based on position
            y_ratio = bbox[1] / page_height if page_height > 0 else 0.5
            if y_ratio < 0.05:
                block_type = "header"
            elif y_ratio > 0.95:
                block_type = "footer"
            else:
                block_type = "paragraph"

            blocks.append(TextBlock(
                page_number=page_number,
                content=content.strip(),
                bbox=bbox,
                confidence=1.0,  # native text has perfect confidence
                block_type=block_type,
            ))

        return blocks
