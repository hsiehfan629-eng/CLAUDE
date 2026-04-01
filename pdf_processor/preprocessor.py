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

        if CONFIG.preprocessing_denoise:
            img = self._denoise(img)

        if CONFIG.preprocessing_clahe:
            img = self._apply_clahe(img)

        if CONFIG.preprocessing_binarize:
            img = self._binarize(img)

        if CONFIG.preprocessing_deskew:
            img = self._deskew(img)

        return img

    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """Remove scanner noise with non-local means denoising."""
        return cv2.fastNlMeansDenoising(image, h=10, templateWindowSize=7,
                                         searchWindowSize=21)

    def _apply_clahe(self, image: np.ndarray) -> np.ndarray:
        """Enhance contrast with CLAHE."""
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
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

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """Correct skew angle using minimum area rectangle on contours."""
        coords = np.column_stack(np.where(image > 0))
        if len(coords) < 100:
            return image

        angle = cv2.minAreaRect(coords)[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        # Only deskew if angle is significant but not too large
        if abs(angle) < 0.5 or abs(angle) > 10:
            return image

        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(
            image, matrix, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
