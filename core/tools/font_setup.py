"""matplotlib 한국어 폰트 설정."""
from __future__ import annotations

from pathlib import Path

import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

_FONT_PROP: fm.FontProperties | None = None
_CONFIGURED = False


def setup_korean_font() -> fm.FontProperties | None:
    """시스템 한글 폰트를 matplotlib에 등록하고 rcParams를 설정."""
    global _FONT_PROP, _CONFIGURED
    if _CONFIGURED:
        return _FONT_PROP

    _CONFIGURED = True
    for path in _FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            fm.fontManager.addfont(path)
        except (OSError, RuntimeError, ValueError):
            continue
        prop = fm.FontProperties(fname=path)
        name = prop.get_name()
        plt.rcParams["font.family"] = name
        plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        _FONT_PROP = prop
        return prop

    plt.rcParams["axes.unicode_minus"] = False
    return None
