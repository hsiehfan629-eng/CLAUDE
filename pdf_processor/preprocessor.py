"""Image preprocessing pipeline for OCR accuracy improvement."""

import numpy as np

from config import CONFIG

try:
    import cv2
except ImportError:
    cv2 = None


class ImagePreprocessor:
    """OpenCV-based image preprocessing for scanned PDF pages."""

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Run the full preprocessing pipeline."""
        if cv2 is None:
            return image

        img = image.copy()

        if CONFIG.preprocessing_grayscale and len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        if CONFIG.preprocessing_deskew:
            img = self._deskew(img)

        if CONFIG.preprocessing_denoise:
            img = self._denoise(img)

        if CONFIG.preprocessing_clahe:
            img = self._apply_clahe(img)

        if CONFIG.preprocessing_binarize:
            img = self._binarize(img)

        if CONFIG.preprocessing_morphological_close:
            img = self._morphological_close(img)

        return img

    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """Remove scanner noise. Tuned for Chinese (h=7 preserves fine strokes)."""
        h = CONFIG.preprocessing_denoise_h
        return cv2.fastNlMeansDenoising(image, h=h, templateWindowSize=7,
                                         searchWindowSize=21)

    def _apply_clahe(self, image: np.ndarray) -> np.ndarray:
        """Enhance contrast with CLAHE (increased clip for scanned docs)."""
        clip = CONFIG.preprocessing_clahe_clip
        clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
        return clahe.apply(image)

    def _binarize(self, image: np.ndarray) -> np.ndarray:
        """Adaptive Gaussian thresholding for uneven lighting."""
        return cv2.adaptiveThreshold(
            image, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )

    def _morphological_close(self, image: np.ndarray) -> np.ndarray:
        """Morphological closing to connect broken Chinese character strokes."""
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        return cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """Correct skew using Hough line transform (more robust than minAreaRect)."""
        max_angle = CONFIG.preprocessing_deskew_max_angle

        # Use Canny edge detection + Hough lines for angle
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=image.shape[1] // 4,
                                maxLineGap=10)

        if lines is None or len(lines) == 0:
            return image

        # Calculate dominant angle from detected lines
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 - x1 == 0:
                continue
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            # Only consider near-horizontal lines (text lines)
            if abs(angle) < max_angle:
                angles.append(angle)

        if not angles:
            return image

        # Use median angle (robust to outliers)
        median_angle = np.median(angles)

        if abs(median_angle) < 0.3:
            return image  # negligible skew

        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        return cv2.warpAffine(
            image, matrix, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
