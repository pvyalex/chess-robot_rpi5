"""
detect_move_optimised.py
------------------------
Simplified move detector for constant-lighting setups.

Changes vs the original StableMoveDetector:
  - EMA removed (only 2 images compared, no multi-frame smoothing needed)
  - _normalize_frame_to_ref removed (constant lighting assumed)
  - CLAHE created once at module level instead of per call
  - Sobel runs on blur-only gray, NOT on CLAHE-enhanced gray
  - Scoring math (separate zI/zE then combine) kept IDENTICAL to original
  - Confidence ratio logic kept IDENTICAL to original
"""

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Board orientation – must match your camera setup
# ---------------------------------------------------------------------------
FLIP_H = True
FLIP_V = True

# ---------------------------------------------------------------------------
# Tuning – same defaults as the original
# ---------------------------------------------------------------------------
INNER_RATIO    = 0.4
Z_MIN          = 2.0
TOP_K          = 6
CONF_RATIO_MIN = 1.12

# Single CLAHE instance reused across all calls
_CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell_roi(img: np.ndarray, r: int, c: int) -> np.ndarray:
    h, w = img.shape[:2]
    ch, cw = h // 8, w // 8
    y0, y1 = r * ch, (r + 1) * ch
    x0, x1 = c * cw, (c + 1) * cw
    py = int((1 - INNER_RATIO) * ch / 2)
    px = int((1 - INNER_RATIO) * cw / 2)
    return img[y0 + py: y1 - py, x0 + px: x1 - px]


def _sq_name(r: int, c: int) -> str:
    file_idx = (7 - c) if FLIP_H else c
    rank_idx = (r + 1) if FLIP_V else (8 - r)
    return f"{chr(ord('a') + file_idx)}{rank_idx}"


def _robust_z(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) + 1e-6
    return (x - med) / (1.4826 * mad + 1e-6)


def _grid_median(img: np.ndarray) -> np.ndarray:
    M = np.zeros((8, 8), dtype=np.float32)
    for r in range(8):
        for c in range(8):
            M[r, c] = float(np.median(_cell_roi(img, r, c)))
    return M


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def _extract_features(img_bgr: np.ndarray):
    """
    Returns (intensity_8x8, edge_8x8).

    Intensity uses blur + CLAHE (same as original).
    Edges use blur-only so CLAHE doesn't artificially inflate Sobel values.
    """
    gray     = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blurred  = cv2.GaussianBlur(gray, (5, 5), 0)
    enhanced = _CLAHE.apply(blurred)   # for intensity only

    I = _grid_median(enhanced)

    # Sobel on blurred (not CLAHE-enhanced) — avoids inflated edge scores
    gx  = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy  = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    E   = _grid_median(cv2.magnitude(gx, gy))

    return I, E


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MoveDetector:
    """
    Compare exactly two board images and return the two squares that changed.

    Usage:
        detector = MoveDetector()
        detector.set_reference(before_bgr)
        pair, info = detector.detect(after_bgr)
    """

    def __init__(self):
        self._ref_I = None
        self._ref_E = None

    def set_reference(self, img_bgr: np.ndarray) -> None:
        self._ref_I, self._ref_E = _extract_features(img_bgr)

    def detect(self, img_bgr: np.ndarray):
        """
        Returns
        -------
        pair : tuple[str, str] | None
        info : dict  with keys 'reliable', 'confidence', 'ranked'
        """
        if self._ref_I is None:
            raise RuntimeError("Call set_reference() before detect().")

        I2, E2 = _extract_features(img_bgr)

        dI = np.abs(I2 - self._ref_I)
        dE = np.abs(E2 - self._ref_E)

        # Original scoring: z-score each signal separately, then combine
        zI = _robust_z(dI)
        zE = _robust_z(dE)
        score = np.maximum(0.7 * zI + 0.3 * zE, 0)

        flat_idx = np.argsort(score.ravel())[::-1]

        ranked = []
        for idx in flat_idx[:TOP_K]:
            r, c = divmod(int(idx), 8)
            s = float(score[r, c])
            if s < Z_MIN:
                break
            ranked.append({"square": _sq_name(r, c), "score": s})

        if len(ranked) < 2:
            return None, {"reliable": False, "confidence": 0.0, "ranked": ranked}

        # Original confidence: top score vs 3rd score
        s1 = ranked[0]["score"]
        s3 = ranked[2]["score"] if len(ranked) >= 3 else 1e-6
        confidence = float(s1 / (s3 + 1e-6))
        reliable   = confidence >= CONF_RATIO_MIN

        pair = (ranked[0]["square"], ranked[1]["square"])
        return pair, {"reliable": reliable, "confidence": confidence, "ranked": ranked}