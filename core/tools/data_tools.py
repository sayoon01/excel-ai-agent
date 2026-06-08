"""데이터 처리 도구 — 필터·집계·정렬·병합."""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from services.file_manager import read_file


# ── 공통 ──────────────────────────────────────────────────────────────────────

def _load_df(
    files_info: list[dict],
    file_idx: int = 0,
    last_result: "pd.DataFrame | None" = None,
) -> pd.DataFrame | None:
    if last_result is not None and isinstance(last_result, pd.DataFrame):
        return last_result.copy()
    if not files_info:
        return None
    entry = files_info[file_idx] if file_idx < len(files_info) else files_info[0]
    return read_file(entry.get("name", ""), sheet_name=entry.get("sheet"))


def _pick_numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _pick_category_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]


# 컬럼 hint 끝에 붙는 조사 — _infer_col 호출 전 떼어내 매칭률을 높임
_PARTICLES = ("으로는", "에는", "에서", "으로", "이라는", "이라",
              "은", "는", "이", "가", "을", "를", "에", "의", "로", "과", "와")


def _strip_particle(s: str) -> str:
    s = s.strip()
    for p in _PARTICLES:
        if s.endswith(p) and len(s) > len(p):
            return s[: -len(p)]
    return s


# LLM 컬럼 매핑 캐시 — (frozenset(컬럼목록), hint) → 컬럼명
_llm_col_cache: dict[tuple, str | None] = {}


def _infer_col(
    df: pd.DataFrame,
    hint: str,
    numeric_only: bool = False,
    text_only: bool = False,
    llm_client=None,
) -> str | None:
    """프롬프트 힌트에서 가장 유사한 컬럼명 추측.

    전략 (우선순위 순):
    1. 문자열 포함: hint가 컬럼명에 포함되거나 컬럼명이 hint에 포함
    2. 편집거리 1 이하: 오타 허용
    3. LLM 매칭: 실제 컬럼 목록을 LLM에 넘겨 의미 기반 매핑 (client 있을 때)
    → 하드코딩된 동의어 사전 없음 — 어떤 도메인 파일이든 동작

    text_only=True 시 텍스트 컬럼만 candidates로. 단 같은 이름의
    텍스트 컬럼이 없으면 fallback으로 전체 컬럼에서 재시도해 빈손 방지.
    """
    h = hint.lower().strip()
    if text_only:
        candidates = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
        # fallback: text 매칭이 없으면 전체 컬럼으로 재시도
        if not candidates:
            candidates = list(df.columns)
    else:
        candidates = [c for c in df.columns
                      if not numeric_only or pd.api.types.is_numeric_dtype(df[c])]

    # 1. 문자열 포함 (대소문자 무시)
    for col in candidates:
        cl = str(col).lower()
        if h in cl or cl in h:
            return col

    # 2. 편집거리 1 (오타 허용, 짧은 힌트 한정)
    if len(h) >= 2:
        for col in candidates:
            cl = str(col).lower()
            if _edit_distance(h, cl) <= 1:
                return col

    # 3. LLM 의미 기반 매칭 (client 있을 때만)
    if llm_client and candidates:
        cache_key = (frozenset(str(c) for c in candidates), h)
        if cache_key in _llm_col_cache:
            return _llm_col_cache[cache_key]

        col_list = ", ".join(f'"{c}"' for c in candidates)
        messages = [{
            "role": "user",
            "content": (
                f"아래 컬럼 목록 중 '{hint}'와 의미상 가장 가까운 컬럼 이름을 "
                f"하나만 정확히 그대로 반환해줘. 없으면 null을 반환해.\n\n"
                f"컬럼 목록: {col_list}"
            ),
        }]
        try:
            raw = "".join(llm_client.chat_stream(messages, "")).strip().strip('"').strip("'")
            matched = next((c for c in candidates if str(c) == raw), None)
            _llm_col_cache[cache_key] = matched
            return matched
        except Exception:
            _llm_col_cache[cache_key] = None

    return None


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein 거리 (최대 길이 20 제한으로 성능 보장)."""
    if abs(len(a) - len(b)) > 3:
        return 99
    a, b = a[:20], b[:20]
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        ndp = [i + 1]
        for j, cb in enumerate(b):
            ndp.append(min(dp[j + 1] + 1, ndp[j] + 1, dp[j] + (ca != cb)))
        dp = ndp
    return dp[-1]


# ── 날짜 필터 헬퍼 ────────────────────────────────────────────────────────────

_DATE_NAME_HINTS = {"일자", "날짜", "date", "기간", "month", "time", "년도", "연도", "월"}


def _find_date_col(df: pd.DataFrame) -> tuple[str | None, "pd.Series | None"]:
    """날짜형 컬럼을 찾고 datetime Series를 반환.

    우선순위:
    1. 이미 datetime64 타입인 컬럼
    2. 컬럼명에 날짜 힌트(일자·날짜·date 등)가 포함된 컬럼 → to_datetime 시도
    3. 임의 object 컬럼 중 50% 이상 파싱 성공하는 것
    """
    candidates: list[str] = []

    datetime_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    candidates.extend(datetime_cols)

    for col in df.columns:
        if col in candidates:
            continue
        if any(h in str(col).lower() for h in _DATE_NAME_HINTS):
            candidates.append(col)

    for col in df.columns:
        if col not in candidates:
            candidates.append(col)

    for col in candidates:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col, df[col]
        series = pd.to_datetime(df[col], errors="coerce")
        if series.notna().mean() >= 0.5:
            return col, series

    return None, None


def _parse_date_range(prompt: str) -> tuple["dt.datetime | None", "dt.datetime | None"]:
    """프롬프트에서 (start, end) datetime 추출. None = 제한 없음.

    지원 패턴:
      절대: "2024년 1월 이후", "2024년 3월 이전",
            "2024년 1월 ~ 2024년 3월", "2024-01-01 이후"
      상대: "올해", "작년", "이번달", "지난달", "1분기"~"4분기"
    """
    today = dt.datetime.now()
    year  = today.year
    start: dt.datetime | None = None
    end:   dt.datetime | None = None

    # ── 절대 날짜 범위: "2024년 1월 ~ 2024년 3월" ─────────────────────────────
    _range = re.search(
        r"(\d{4})년?\s*(\d{1,2})?월?\s*(?:~|부터|에서)\s*(\d{4})?년?\s*(\d{1,2})월",
        prompt,
    )
    if _range:
        sy = int(_range.group(1))
        sm = int(_range.group(2) or 1)
        ey = int(_range.group(3) or sy)
        em = int(_range.group(4))
        start = dt.datetime(sy, sm, 1)
        end   = dt.datetime(ey + 1, 1, 1) if em == 12 else dt.datetime(ey, em + 1, 1)
        return start, end

    # ── 단방향 절대 날짜 ──────────────────────────────────────────────────────
    _after = re.search(r"(\d{4})년\s*(\d{1,2})?월?\s*(?:이후|이상|부터)", prompt)
    _before = re.search(r"(\d{4})년\s*(\d{1,2})?월?\s*(?:이전|이하|까지)", prompt)
    if _after:
        sy = int(_after.group(1));  sm = int(_after.group(2) or 1)
        start = dt.datetime(sy, sm, 1)
    if _before:
        by = int(_before.group(1)); bm = int(_before.group(2) or 12)
        end = dt.datetime(by + 1, 1, 1) if bm == 12 else dt.datetime(by, bm + 1, 1)
    if start or end:
        return start, end

    # ── ISO 날짜: "2024-01-15 이후" ──────────────────────────────────────────
    _iso_a = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})\s*(?:이후|이상|부터)", prompt)
    _iso_b = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})\s*(?:이전|이하|까지)", prompt)
    if _iso_a:
        try: start = pd.Timestamp(_iso_a.group(1)).to_pydatetime()
        except Exception: pass
    if _iso_b:
        try: end = pd.Timestamp(_iso_b.group(1)).to_pydatetime() + dt.timedelta(days=1)
        except Exception: pass
    if start or end:
        return start, end

    # ── 상대 날짜 ─────────────────────────────────────────────────────────────
    if "올해" in prompt:
        start = dt.datetime(year, 1, 1);      end = dt.datetime(year + 1, 1, 1)
    elif "작년" in prompt or "지난해" in prompt:
        start = dt.datetime(year - 1, 1, 1);  end = dt.datetime(year, 1, 1)
    elif "이번달" in prompt or "이번 달" in prompt:
        start = dt.datetime(year, today.month, 1)
        end   = dt.datetime(year + 1, 1, 1) if today.month == 12 \
                else dt.datetime(year, today.month + 1, 1)
    elif "지난달" in prompt or "지난 달" in prompt:
        if today.month == 1:
            start = dt.datetime(year - 1, 12, 1); end = dt.datetime(year, 1, 1)
        else:
            start = dt.datetime(year, today.month - 1, 1)
            end   = dt.datetime(year, today.month, 1)

    # ── 분기 ─────────────────────────────────────────────────────────────────
    _q = re.search(r"([1-4])분기", prompt)
    if _q:
        q  = int(_q.group(1))
        qm = (q - 1) * 3 + 1
        qy_m = re.search(r"(\d{4})년", prompt)
        qy   = int(qy_m.group(1)) if qy_m else year
        start = dt.datetime(qy, qm, 1)
        em, ey = qm + 3, qy
        if em > 12: em -= 12; ey += 1
        end = dt.datetime(ey, em, 1)

    return start, end


# ── 컬럼 선택 ────────────────────────────────────────────────────────────────

# "X만", "X와 Y만 보여줘", "이름, 연봉, 부서 컬럼" 같은 표현에서 컬럼 추출.
# select_columns 라우팅과 함께 쓰임.
_SELECT_NOISE = {
    "보여줘", "보여", "추출", "추출해줘", "추출해", "선택", "선택해", "골라",
    "표시", "표시해", "노출", "리스트", "list",
    "컬럼", "컬럼만", "열", "열만", "열로",
    "그리고", "그 외", "외에", "외", "포함",
}


def select_columns(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """프롬프트에 명시된 컬럼만 추출(projection).

    지원 패턴:
      - "X만 보여줘", "X 컬럼만"
      - "X, Y, Z 컬럼", "X와 Y만"
      - "이름, 부서, 연봉 만"

    Returns:
        {"type": "dataframe", "value": pd.DataFrame, "label": str}
    """
    df = _load_df(files_info, last_result=kwargs.get("last_result"))
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    llm_client = kwargs.get("llm_client")

    # 1) 명시 컬럼 토큰 — 콤마·"와"·"과" 구분자로 분할 후 _infer_col
    #    "X만/X컬럼만"의 "만/컬럼만"은 잡음. 조사도 제거.
    tokens: list[str] = []
    for raw in re.split(r"[,\s]+|와\s+|과\s+|및\s+", prompt):
        tok = _strip_particle(raw.strip())
        # 어미 정리: "비목분류만" → "비목분류", "당년도집행을" → "당년도집행"
        tok = re.sub(r"(만|만을|만은|만이|을|를|이|가)$", "", tok)
        if not tok or len(tok) < 2:
            continue
        if tok.lower() in _SELECT_NOISE:
            continue
        tokens.append(tok)

    selected: list[str] = []
    for tok in tokens:
        cand = _infer_col(df, tok, llm_client=llm_client)
        if cand is not None and cand not in selected:
            selected.append(cand)

    if not selected:
        return {
            "type": "error",
            "message": "추출할 컬럼을 찾지 못했습니다. 예: '비목분류만 보여줘', '이름, 연봉 컬럼'",
        }

    result = df[selected].copy().reset_index(drop=True)
    return {
        "type": "dataframe",
        "value": result,
        "label": "컬럼 추출",
        "summary": (
            f"{len(df.columns)}컬럼 → {len(selected)}컬럼 ({len(result):,}행). "
            f"선택: {', '.join(map(str, selected))}"
        ),
    }


# ── 집계 ─────────────────────────────────────────────────────────────────────

def aggregate_data(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """합계·평균·최대·최소 집계. groupby 키워드 감지 시 그룹별 집계.

    지원 패턴:
      - 단순 집계  : "합계", "평균", "최대", "최소"
      - 그룹별 집계: "X별 합계", "Y별 평균", "Z별 최대"

    Returns:
        {"type": "dataframe", "value": pd.DataFrame, "label": str}
    """
    df = _load_df(files_info, last_result=kwargs.get("last_result"))
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    numeric_cols = _pick_numeric_cols(df)
    if not numeric_cols:
        return {"type": "error", "message": "수치형 컬럼이 없습니다."}

    p = prompt.lower()

    # ── 집계 함수 감지 ────────────────────────────────────────────────────────
    agg_map: dict[str, str] = {}
    if any(k in p for k in ["합계", "총합", "sum", "총액"]):
        agg_map["합계"] = "sum"
    if any(k in p for k in ["평균", "mean", "avg", "평균값"]):
        agg_map["평균"] = "mean"
    if any(k in p for k in ["최대", "max", "최댓값"]):
        agg_map["최대"] = "max"
    if any(k in p for k in ["최소", "min", "최솟값"]):
        agg_map["최소"] = "min"
    if any(k in p for k in ["개수", "count", "건수", "몇 개"]):
        agg_map["개수"] = "count"
    if not agg_map:
        agg_map = {"합계": "sum", "평균": "mean", "최대": "max", "최소": "min"}

    llm_client = kwargs.get("llm_client")

    # ── groupby 컬럼 감지 — "X별" 패턴 (텍스트 컬럼 우선) ───────────────────
    _groupby_pat = re.search(r"([\w가-힣]+)별", prompt)
    group_col: str | None = None
    group_hint: str = ""
    if _groupby_pat:
        group_hint = _groupby_pat.group(1)
        group_col = _infer_col(df, group_hint, text_only=True, llm_client=llm_client)
        if group_col and pd.api.types.is_numeric_dtype(df[group_col]):
            group_col = None
        if group_col is None:
            cat_cols = _pick_category_cols(df)
            if cat_cols:
                group_col = cat_cols[0]
                group_hint = f"{group_hint}(→{group_col})"

    # ── 대상 값 컬럼 추출 — prompt에 명시된 수치 컬럼만 집계 ─────────────────
    # "비목분류별 당년도집행 합계" → 모든 수치 컬럼이 아니라 '당년도집행' 하나만.
    # 명시된 컬럼이 없으면 기존처럼 모든 수치 컬럼 (전체 집계).
    _AGG_FUNC_KW = {
        "합계","총합","총액","sum",
        "평균","평균값","mean","avg",
        "최대","최댓값","max","최소","최솟값","min",
        "개수","건수","count",
        "그룹","group","기준","별로","별",
    }
    target_cols: list[str] = []
    # 1) 수치 컬럼명이 prompt에 직접 substring으로 등장
    #    group_hint(예: "비용명별"의 "비용명")는 그룹 키 단서이므로 값 컬럼에서 제외.
    _exclude_hints = {group_hint.split("(")[0]} if group_hint else set()
    for c in numeric_cols:
        if c == group_col:
            continue
        if str(c) in _exclude_hints:
            continue
        if str(c).lower() in p:
            target_cols.append(c)
    # 2) 토큰 단위 _infer_col — 1단계와 별개로 항상 시도. 컬럼명이 정확하지 않은
    #    힌트(예: "실행예산"이라는 단어가 prompt엔 있는데 컬럼은 "실행예산_합계"
    #    뿐인 경우)에서 빠진 컬럼을 보강.
    for tok in re.findall(r"[\w가-힣]{2,}", prompt):
        tok2 = _strip_particle(tok)
        tok2_l = tok2.lower()
        if tok2_l in _AGG_FUNC_KW or tok2_l.endswith("별"):
            continue
        if group_col and tok2 == group_col:
            continue
        if tok2 in _exclude_hints:
            continue
        # 이미 1단계에서 잡힌 컬럼은 스킵 (속도)
        if any(tok2 in str(c) or str(c) in tok2 for c in target_cols):
            continue
        cand = _infer_col(df, tok2, numeric_only=True, llm_client=llm_client)
        if cand and cand != group_col and cand not in target_cols:
            target_cols.append(cand)
    # 3) 그래도 없으면 모든 수치 컬럼
    agg_cols = target_cols if target_cols else [c for c in numeric_cols if c != group_col]
    cols_note = ""
    if target_cols:
        cols_note = f" — 컬럼: {', '.join(map(str, target_cols))}"

    if group_col:
        # 그룹별 집계
        pandas_agg = {v: v for v in set(agg_map.values())}
        label_map  = {v: k for k, v in agg_map.items()}

        grouped = df.groupby(group_col)[agg_cols].agg(list(pandas_agg.keys()))
        grouped.columns = [
            f"{col}_{label_map.get(fn, fn)}"
            for col, fn in grouped.columns
        ]
        result = grouped.reset_index()
        if len(result.columns) > 1:
            result = result.sort_values(result.columns[1], ascending=False)

        inferred_note = f" ('{group_hint}' → '{group_col}' 컬럼 사용)" if "→" in group_hint else ""
        return {
            "type": "dataframe",
            "value": result.reset_index(drop=True),
            "label": f"{group_col}별 집계",
            "summary": (
                f"{group_col} 기준 {len(result)}개 그룹, "
                f"{'·'.join(agg_map.keys())} 집계 완료{inferred_note}{cols_note}"
            ),
        }

    # ── 단순 집계 (groupby 없음) ──────────────────────────────────────────────
    rows = []
    for col in agg_cols:
        row: dict = {"컬럼": col}
        for label, func in agg_map.items():
            row[label] = getattr(df[col], func)()
        rows.append(row)

    result = pd.DataFrame(rows)
    for col in result.columns:
        if col != "컬럼" and pd.api.types.is_numeric_dtype(result[col]):
            result[col] = result[col].round(4)

    return {
        "type": "dataframe",
        "value": result,
        "label": "집계 결과",
        "summary": f"{len(agg_cols)}개 수치 컬럼 {'·'.join(agg_map.keys())} 집계 완료{cols_note}",
    }


# ── 필터 ──────────────────────────────────────────────────────────────────────

def filter_rows(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """조건 기반 필터. 아래 패턴을 순서대로 시도한다.

    지원 패턴:
      - 상위/하위 N개    : "상위 10개", "하위 5행", "top 3"
      - 숫자 비교       : "값 >= 1000", "수치 이상 30", "숫자컬럼 > 80"
      - 문자열 포함/제외 : "텍스트컬럼에 '키워드' 포함", "구분컬럼 값X 제외"
      - 컬럼 비교       : "A컬럼이 B컬럼보다 큰" (수치 컬럼 간)
      - 결측 제거       : "결측 제거", "빈칸 제거"
    """
    df = _load_df(files_info, last_result=kwargs.get("last_result"))
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    llm_client = kwargs.get("llm_client")
    original_len = len(df)
    applied: list[str] = []

    # ── 1. 상위/하위 N개 ──────────────────────────────────────────────────────
    _top_pat = re.search(
        r"(상위|top|최상위|크기순|높은)\s*(\d+)\s*(?:개|행|건|rows?)?", prompt, re.I
    )
    _bot_pat = re.search(
        r"(하위|bottom|최하위|낮은)\s*(\d+)\s*(?:개|행|건|rows?)?", prompt, re.I
    )
    if _top_pat or _bot_pat:
        pat  = _top_pat or _bot_pat
        n    = int(pat.group(2))  # type: ignore[union-attr]
        asc  = bool(_bot_pat)
        nums = _pick_numeric_cols(df)
        sort_col = next(
            (c for c in df.columns if str(c).lower() in prompt.lower()),
            nums[0] if nums else df.columns[0],
        )
        df = df.nsmallest(n, sort_col) if asc else df.nlargest(n, sort_col)
        applied.append(f"{'하위' if asc else '상위'} {n}개 ({sort_col})")

    # ── 2. 숫자 비교 (한국어 어순 우선: 컬럼+조사 + 숫자 + 연산자) ────────────
    # 영문식 "컬럼 op 값"도 보조 패턴으로 지원.
    _OP_K = {
        "이상": ">=", "≥": ">=", "이하": "<=", "≤": "<=",
        "초과": ">",  "보다 큰": ">",  "보다 많은": ">",  "보다 높은": ">",
        "미만": "<",  "보다 작은": "<", "보다 적은": "<", "보다 낮은": "<",
    }
    _NUM_KO_PAT = (
        r"([\w가-힣]+?)(?:이|가|은|는|을|를)?\s+"
        r"(\d[\d,]*(?:\.\d+)?)\s*"
        r"(이상|이하|초과|미만|≥|≤|보다\s*큰|보다\s*많은|보다\s*높은|보다\s*작은|보다\s*적은|보다\s*낮은)"
    )
    _applied_masks: list[tuple[str, str, float]] = []  # 범위 중복 방지
    for m in re.finditer(_NUM_KO_PAT, prompt):
        col_hint = _strip_particle(m.group(1))
        val      = float(m.group(2).replace(",", ""))
        kw       = re.sub(r"\s+", " ", m.group(3))
        op       = _OP_K.get(kw, ">=")
        col = _infer_col(df, col_hint, llm_client=llm_client)
        if not col or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        # 컬럼 hint가 숫자만으로 추론된 경우(예: 범위의 두 번째 숫자) — 직전 컬럼 재사용
        if col_hint.isdigit() and _applied_masks:
            col = _applied_masks[-1][0]
        mask = {
            ">=": df[col] >= val, "<=": df[col] <= val,
            ">":  df[col] >  val, "<":  df[col] <  val,
        }[op]
        df = df[mask]
        _applied_masks.append((col, op, val))
        applied.append(f"{col} {op} {val:,g}")

    # 영문식 보조 — "컬럼 >= 1000"
    _NUM_EN_PATS = [
        (r"([\w가-힣]+?)\s*(>=|≥)\s*(\d[\d,]*(?:\.\d+)?)", ">="),
        (r"([\w가-힣]+?)\s*(<=|≤)\s*(\d[\d,]*(?:\.\d+)?)", "<="),
        (r"([\w가-힣]+?)\s*(>)\s*(\d[\d,]*(?:\.\d+)?)",   ">"),
        (r"([\w가-힣]+?)\s*(<)\s*(\d[\d,]*(?:\.\d+)?)",   "<"),
    ]
    for pat, op in _NUM_EN_PATS:
        for m in re.finditer(pat, prompt):
            col_hint = _strip_particle(m.group(1))
            col = _infer_col(df, col_hint, llm_client=llm_client)
            if not col or not pd.api.types.is_numeric_dtype(df[col]):
                continue
            val = float(m.group(3).replace(",", ""))
            tag = f"{col} {op} {val:,g}"
            if tag in applied:
                continue
            mask = {">=": df[col] >= val, "<=": df[col] <= val,
                    ">":  df[col] >  val, "<":  df[col] <  val}[op]
            df = df[mask]
            applied.append(tag)

    # ── 3. 문자열 포함/제외 — "들어간/들어있는/포함된/포함" ────────────────────
    # 키워드가 따옴표 안에 있을 때 우선 추출 → 조사 흡수 방지
    _INC_KW = r"(?:포함|들어간|들어있|들어가|있는|포함된|contains?)"
    _EXC_KW = r"(?:제외|exclude|빼|except)"
    _STR_PATS = [
        # "비목분류에 '운영'이 들어간" — 따옴표 명시
        (r"([\w가-힣]+?)(?:에|에서|에는)?\s*['\"]([^'\"]+?)['\"](?:이|가|은|는)?\s*" + _INC_KW, True),
        # 따옴표 없는 형태 — "비용명에 회의 포함"
        (r"([\w가-힣]+?)(?:에|에서|에는)?\s+([\w가-힣A-Za-z0-9]+?)(?:이|가|은|는)?\s*" + _INC_KW, True),
        # 제외
        (r"([\w가-힣]+?)(?:에|에서|에는)?\s*['\"]([^'\"]+?)['\"](?:이|가|은|는)?\s*" + _EXC_KW, False),
        (r"([\w가-힣]+?)(?:에|에서|에는)?\s+([\w가-힣A-Za-z0-9]+?)(?:이|가|은|는)?\s*" + _EXC_KW, False),
    ]
    _str_applied: set[tuple[str, str, bool]] = set()
    for pat, include in _STR_PATS:
        for m in re.finditer(pat, prompt):
            col_hint = _strip_particle(m.group(1))
            keyword  = m.group(2).strip("'\"")
            # 텍스트 컬럼 우선 — "비용명"이 코드숫자(float)인 경우 진짜 텍스트 컬럼으로
            col = _infer_col(df, col_hint, text_only=True, llm_client=llm_client)
            if not col or pd.api.types.is_numeric_dtype(df[col]):
                continue
            key = (col, keyword, include)
            if key in _str_applied:
                continue
            mask = df[col].astype(str).str.contains(keyword, na=False, regex=False)
            df = df[mask] if include else df[~mask]
            _str_applied.add(key)
            applied.append(f"{col} {'포함' if include else '제외'} '{keyword}'")

    # ── 4. 컬럼 간 비교 — 양쪽 어순 + "을/를 초과" 지원 ───────────────────────
    # "A보다 B가 더 큰" / "B가 A보다 큰" / "A가 B를 초과한"
    _COL_CMP_PATS = [
        # A보다 B가 (더) 큰  → B > A
        (r"([\w가-힣]+?)(?:보다)\s+([\w가-힣]+?)(?:이|가|은|는)?\s*(?:더\s*)?(큰|많은|높은|초과)", "B>A"),
        (r"([\w가-힣]+?)(?:보다)\s+([\w가-힣]+?)(?:이|가|은|는)?\s*(?:더\s*)?(작은|적은|낮은|미만)", "B<A"),
        # B가 A보다 (더) 큰  → B > A
        (r"([\w가-힣]+?)(?:이|가|은|는)\s+([\w가-힣]+?)(?:보다)\s*(?:더\s*)?(큰|많은|높은|초과)", "A>B"),
        (r"([\w가-힣]+?)(?:이|가|은|는)\s+([\w가-힣]+?)(?:보다)\s*(?:더\s*)?(작은|적은|낮은|미만)", "A<B"),
        # A가 B를 초과/미만 — "당년도집행이 계획예산을 초과한" → A > B
        (r"([\w가-힣]+?)(?:이|가|은|는)\s+([\w가-힣]+?)(?:을|를)\s*(초과|보다\s*큰|보다\s*많|보다\s*높)", "A>B"),
        (r"([\w가-힣]+?)(?:이|가|은|는)\s+([\w가-힣]+?)(?:을|를)\s*(미만|보다\s*작|보다\s*적|보다\s*낮)", "A<B"),
    ]
    for pat, direction in _COL_CMP_PATS:
        m = re.search(pat, prompt)
        if not m:
            continue
        ca = _infer_col(df, _strip_particle(m.group(1)), llm_client=llm_client)
        cb = _infer_col(df, _strip_particle(m.group(2)), llm_client=llm_client)
        if not (ca and cb) or ca == cb: continue
        if not (pd.api.types.is_numeric_dtype(df[ca]) and pd.api.types.is_numeric_dtype(df[cb])):
            continue
        if direction == "B>A":   df = df[df[cb] >  df[ca]]; tag = f"{cb} > {ca}"
        elif direction == "B<A": df = df[df[cb] <  df[ca]]; tag = f"{cb} < {ca}"
        elif direction == "A>B": df = df[df[ca] >  df[cb]]; tag = f"{ca} > {cb}"
        else:                    df = df[df[ca] <  df[cb]]; tag = f"{ca} < {cb}"
        applied.append(tag)
        break  # 한 번만 적용

    # ── 5. 결측치 — 전체 제거 / 특정 컬럼 비어있는 행 추출 ────────────────────
    if any(k in prompt for k in ["결측 제거", "빈칸 제거", "null 제거", "결측값 제거", "na 제거"]):
        before = len(df)
        df = df.dropna()
        applied.append(f"결측 제거 ({before - len(df)}행 삭제)")

    # "컬럼이 비어있는/비었/공백/null/없는" → 해당 컬럼이 NA인 행만 남김
    _NULL_PAT = (
        r"([\w가-힣]+?)(?:이|가|은|는)\s*(?:값이?\s*)?"
        r"(비어\s*있는|비어있|비었|공백|null|na|없는|없음)"
    )
    for m in re.finditer(_NULL_PAT, prompt, re.I):
        col = _infer_col(df, _strip_particle(m.group(1)), llm_client=llm_client)
        if not col:
            continue
        # 결측 + 빈 문자열 모두 처리
        ser = df[col]
        mask = ser.isna()
        if ser.dtype == object:
            mask = mask | ser.astype(str).str.strip().isin(["", "nan", "None"])
        df = df[mask]
        applied.append(f"{col} 비어있는 행")
        break

    # ── 6. 숫자 같음 — "컬럼이 숫자인 것" ──────────────────────────────────────
    _num_eq = re.search(
        r"([\w가-힣]+?)(?:이|가|은|는)\s+(\d[\d,]*(?:\.\d+)?)\s*인", prompt
    )
    if _num_eq:
        col = _infer_col(df, _strip_particle(_num_eq.group(1)), llm_client=llm_client)
        if col and pd.api.types.is_numeric_dtype(df[col]):
            val = float(_num_eq.group(2).replace(",", ""))
            df = df[df[col] == val]
            applied.append(f"{col} == {val:,g}")

    # ── 7. 문자열 같음 — "컬럼이 '값'인", "컬럼 == 값" ────────────────────────
    _str_eq_pats = [
        # 따옴표 값 우선: "비목분류가 '인건비'인 행"
        r"([\w가-힣]+?)(?:이|가|은|는)\s*['\"]([^'\"]+?)['\"]\s*(?:인|이다|와\s*같)",
        # 따옴표 없음: "비목분류가 인건비인 행"
        r"([\w가-힣]+?)(?:이|가|은|는)\s+([\w가-힣A-Za-z0-9_\-\.]+?)(?=인\s*(?:것|행|항목|데이터)?(?:\s|$)|이다(?:\s|$))",
        # 영문식: "컬럼 = 값" / "컬럼 == 값"
        r"([\w가-힣]+?)\s*(?:==|=)\s*['\"]?([\w가-힣A-Za-z0-9_\-\.]+)['\"]?",
    ]
    for _sep in _str_eq_pats:
        for m in re.finditer(_sep, prompt):
            col_hint = _strip_particle(m.group(1))
            val = m.group(2).strip("'\"")
            col = _infer_col(df, col_hint, text_only=True, llm_client=llm_client)
            if col is None or pd.api.types.is_numeric_dtype(df[col]):
                continue
            # 정확 일치 우선, 없으면 부분 포함 fallback
            #  ("인건비" → 실제 값 "내부인건비"처럼 부분 일치)
            eq_mask  = df[col].astype(str) == val
            sub_mask = df[col].astype(str).str.contains(val, na=False, regex=False)
            if eq_mask.sum() > 0:
                mask, tag = eq_mask, f"{col} == '{val}'"
            elif sub_mask.sum() > 0:
                mask, tag = sub_mask, f"{col} 포함 '{val}'"
            else:
                continue
            if tag not in applied:
                df = df[mask]
                applied.append(tag)

    # ── 8. 날짜 범위 필터 ────────────────────────────────────────────────────
    _dt_start, _dt_end = _parse_date_range(prompt)
    if _dt_start is not None or _dt_end is not None:
        _date_col, _date_series = _find_date_col(df)
        if _date_col and _date_series is not None:
            mask = pd.Series([True] * len(df), index=df.index)
            if _dt_start:
                mask &= _date_series >= pd.Timestamp(_dt_start)
            if _dt_end:
                mask &= _date_series < pd.Timestamp(_dt_end)
            df = df[mask.values]
            if _dt_start and _dt_end:
                _range_label = f"{_dt_start.strftime('%Y-%m')} ~ {_dt_end.strftime('%Y-%m')}"
            elif _dt_start:
                _range_label = f"{_dt_start.strftime('%Y-%m-%d')} 이후"
            else:
                _range_label = f"{_dt_end.strftime('%Y-%m-%d')} 이전"
            applied.append(f"{_date_col} [{_range_label}]")

    if not applied:
        _num_ex  = str(_pick_numeric_cols(df)[0])  if _pick_numeric_cols(df)  else "값"
        _cat_ex  = str(_pick_category_cols(df)[0]) if _pick_category_cols(df) else "항목"
        summary = (
            f"조건을 파악하지 못했습니다. "
            f"예: '{_num_ex} >= 1000', '상위 10개', '{_cat_ex}이 값인 것'"
        )
    else:
        summary = f"필터 적용: {', '.join(applied)}"

    return {
        "type": "dataframe",
        "value": df.reset_index(drop=True),
        "label": "필터 결과",
        "summary": f"{original_len:,}행 → {len(df):,}행. {summary}",
    }


# ── 정렬 ──────────────────────────────────────────────────────────────────────

_SORT_DESC_KW = (
    "내림차순", "descending", "desc",
    "큰 순", "큰순", "높은 순", "높은순", "많은 순", "많은순",
    "내림", "역순", "감소",
)
_SORT_ASC_KW = (
    "오름차순", "ascending", "asc",
    "작은 순", "작은순", "낮은 순", "낮은순", "적은 순", "적은순",
    "오름", "증가", "가나다순", "가나다 순",
)
# 방향 표현 정규식 (한국어 자연어 + 영문 — 멀티컬럼 패턴에서 사용)
_DIRECTION_RE = (
    r"오름차순|내림차순|ascending|descending|asc|desc|"
    r"큰\s*순(?:서|으로)?|작은\s*순(?:서|으로)?|"
    r"높은\s*순(?:서|으로)?|낮은\s*순(?:서|으로)?|"
    r"많은\s*순(?:서|으로)?|적은\s*순(?:서|으로)?|"
    r"가나다\s*순(?:서|으로)?"
)


def _direction_is_asc(word: str) -> bool:
    w = re.sub(r"\s+", " ", word.lower().strip())
    if any(k in w for k in _SORT_DESC_KW):
        return False
    return True


def sort_rows(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """정렬. 멀티컬럼 + 한국어 방향어 지원.

    지원 패턴:
      - 단일: "당년도집행 큰 순", "비목분류 가나다순", "값 내림차순"
      - 멀티: "A컬럼 오름차순, B컬럼 내림차순", "A asc B desc"
    방향 키워드: 내림차순/큰순/높은순/많은순/역순/감소,
                 오름차순/작은순/낮은순/적은순/가나다순
    """
    df = _load_df(files_info, last_result=kwargs.get("last_result"))
    if df is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    llm_client = kwargs.get("llm_client")

    # ── 멀티/단일 (컬럼+방향) 패턴 감지 ───────────────────────────────────────
    _multi_pat = re.findall(
        rf"([\w가-힣]+?)(?:\s*기준)?\s*({_DIRECTION_RE})",
        prompt, re.I,
    )

    sort_cols: list[str] = []
    sort_asc:  list[bool] = []
    used_hints: list[str] = []

    for col_hint, direction_word in _multi_pat:
        col_hint = _strip_particle(col_hint)
        # 방향어가 컬럼 위치에 들어온 경우 (예: "큰 순"이 col_hint로 잡힘) 스킵
        if any(k in col_hint for k in ("순", "차순")):
            continue
        col = _infer_col(df, col_hint, llm_client=llm_client)
        if not col or col in sort_cols:
            continue
        asc = _direction_is_asc(direction_word)
        sort_cols.append(col)
        sort_asc.append(asc)
        used_hints.append(f"{col} {'오름↑' if asc else '내림↓'}")

    if not sort_cols:
        # 멀티 패턴 없음 → 단일 컬럼 추론
        # 방향: 내림차순 키워드가 prompt에 있으면 desc, 아니면 asc 기본
        default_asc = not any(k in prompt for k in _SORT_DESC_KW)

        # 컬럼 매칭: 정확 일치(공백 단위) 우선 → 양방향 부분 매칭(_infer_col) → 첫 수치 컬럼
        col = None
        tokens = set(re.findall(r"[\w가-힣]+", prompt))
        for c in df.columns:
            if str(c) in tokens:
                col = c
                break
        if col is None:
            # prompt에서 방향/공통어를 제거한 토큰으로 _infer_col
            stripped = re.sub(_DIRECTION_RE, " ", prompt, flags=re.I)
            stripped = re.sub(r"\b(기준|정렬|순으로|순)\b", " ", stripped)
            for tok in re.findall(r"[\w가-힣]+", stripped):
                tok = _strip_particle(tok)
                if len(tok) < 2:
                    continue
                cand = _infer_col(df, tok, llm_client=llm_client)
                if cand:
                    col = cand
                    break
        if col is None:
            nums = _pick_numeric_cols(df)
            col = nums[0] if nums else df.columns[0]

        sort_cols = [col]
        sort_asc  = [default_asc]
        used_hints = [f"{col} {'오름↑' if default_asc else '내림↓'}"]

    result = df.sort_values(sort_cols, ascending=sort_asc).reset_index(drop=True)
    summary = ", ".join(used_hints)
    return {
        "type": "dataframe",
        "value": result,
        "label": "정렬 결과",
        "summary": f"{summary} 정렬 ({len(result):,}행)",
    }


# ── 병합 ──────────────────────────────────────────────────────────────────────

def merge_files(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """두 파일 병합 (공통 컬럼 기준 left join, 없으면 단순 concat).

    Returns:
        {"type": "dataframe", "value": pd.DataFrame, "label": str}
    """
    if len(files_info) < 2:
        # 파일 1개면 그냥 반환
        df = _load_df(files_info)
        if df is None:
            return {"type": "error", "message": "병합할 파일이 2개 이상 필요합니다."}
        return {
            "type": "dataframe",
            "value": df,
            "label": "파일 (1개)",
            "summary": "파일이 1개뿐이어서 병합 없이 반환했습니다.",
        }

    df_left = _load_df(files_info, 0)
    df_right = _load_df(files_info, 1)
    if df_left is None or df_right is None:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}

    # 공통 컬럼 중 unique 비율이 가장 높은 컬럼을 키로 선택
    common = list(set(df_left.columns) & set(df_right.columns))
    if not common:
        return {
            "type": "error",
            "message": (
                f"두 파일에 공통 컬럼이 없어 수평 결합(join)을 할 수 없습니다.\n"
                f"  • {files_info[0]['name']} 컬럼: {list(df_left.columns[:5])}\n"
                f"  • {files_info[1]['name']} 컬럼: {list(df_right.columns[:5])}\n"
                "수직 통합(concat)이 필요하다면 '세로로 합쳐줘'처럼 요청하거나, "
                "join 기준이 될 공통 키 컬럼을 알려 주세요."
            ),
        }

    non_numeric = [c for c in common if not pd.api.types.is_numeric_dtype(df_left[c])]
    candidates = non_numeric if non_numeric else common
    key_col = max(candidates, key=lambda c: df_left[c].nunique() / max(len(df_left), 1))
    result = pd.merge(df_left, df_right, on=key_col, how="left")
    method = f"{key_col} 기준 left join"

    return {
        "type": "dataframe",
        "value": result,
        "label": "병합 결과",
        "summary": (
            f"{files_info[0]['name']} + {files_info[1]['name']} → "
            f"{len(result):,}행 × {len(result.columns)}컬럼 ({method})"
        ),
    }


# ── 동일 양식 파일 통합 ───────────────────────────────────────────────────────

def _infer_key_cols(
    df: pd.DataFrame,
    prompt: str,
    common_cols: list[str],
) -> list[str]:
    """동일 양식 통합의 기준 키 컬럼 추론.

    1. 프롬프트에서 언급된 텍스트 컬럼 → key_cols
    2. 없으면 common_cols 중 텍스트 컬럼 전부 → key_cols
    """
    prompt_lower = prompt.lower()
    hinted = [
        c for c in common_cols
        if str(c).lower() in prompt_lower
        and not pd.api.types.is_numeric_dtype(df[c])
    ]
    if hinted:
        return hinted
    return [c for c in common_cols if not pd.api.types.is_numeric_dtype(df[c])]


def merge_same_format(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """동일 양식(같은 구조) 파일 통합.

    concat → groupby(key_cols) → numeric mean + text first → 원본 컬럼 순서 유지.

    key_cols 추론:
        - 프롬프트에 컬럼명이 언급된 경우 → 해당 텍스트 컬럼
        - 아니면 모든 파일에 공통인 텍스트(비수치) 컬럼 전부

    절대 하지 않는 것:
        - pd.merge 가로 병합
        - df.mean() 컬럼별 요약표 생성
    """
    if not files_info:
        return {"type": "error", "message": "파일이 없습니다."}

    # 1. 모든 파일 로드
    dfs: list[pd.DataFrame] = []
    for i in range(len(files_info)):
        df = _load_df(files_info, i)
        if df is not None:
            dfs.append(df)

    if not dfs:
        return {"type": "error", "message": "파일을 읽을 수 없습니다."}
    if len(dfs) == 1:
        return {
            "type": "dataframe",
            "value": dfs[0],
            "label": "파일 (1개)",
            "summary": "파일이 1개뿐입니다.",
        }

    # 2. 공통 컬럼 (첫 번째 파일 순서 기준)
    common_cols = [c for c in dfs[0].columns if all(c in df.columns for df in dfs[1:])]
    if not common_cols:
        return {"type": "error", "message": "파일 간 공통 컬럼이 없습니다. 동일 양식 파일인지 확인하세요."}

    # 3. 세로 concat (공통 컬럼만)
    combined = pd.concat([df[common_cols] for df in dfs], ignore_index=True)

    # 3-1. 소계/합계 행 제거 — 모든 텍스트 컬럼 대상 (벡터화)
    _SUBTOTAL_PATTERNS = {"소 계", "소계", "합 계", "합계", "계", "총계", "총 계",
                          "내부흡수액", "소  계", "합  계"}
    _text_cols_for_filter = [
        c for c in common_cols if not pd.api.types.is_numeric_dtype(combined[c])
    ]
    if _text_cols_for_filter:
        _is_subtotal = combined[_text_cols_for_filter].apply(
            lambda col: col.astype(str).str.strip().isin(_SUBTOTAL_PATTERNS)
        ).any(axis=1)
        combined = combined[~_is_subtotal].reset_index(drop=True)

    # 4. 기준 키 컬럼 추론
    key_cols = _infer_key_cols(dfs[0], prompt, common_cols)
    if not key_cols:
        return {"type": "error", "message": "기준 키 컬럼(텍스트 컬럼)을 찾을 수 없습니다."}

    # 5. 집계 — numeric: mean / text: first
    numeric_cols = [
        c for c in common_cols
        if pd.api.types.is_numeric_dtype(combined[c]) and c not in key_cols
    ]
    text_cols = [
        c for c in common_cols
        if c not in key_cols and c not in numeric_cols
    ]

    # 수치형이지만 그룹 내 값이 항상 동일한 컬럼(항목 코드·ID)은 mean 대신 first
    # ex) 비용명=121은 같은 항목이면 항상 121 → 평균 내면 안 됨
    agg_dict: dict = {}
    for c in numeric_cols:
        within_group_max_nunique = combined.groupby(key_cols, dropna=False)[c].nunique().max()
        agg_dict[c] = "first" if within_group_max_nunique <= 1 else "mean"
    agg_dict.update({c: "first" for c in text_cols})

    code_cols = [c for c in numeric_cols if agg_dict[c] == "first"]
    measure_cols = [c for c in numeric_cols if agg_dict[c] == "mean"]

    if agg_dict:
        result = combined.groupby(key_cols, as_index=False, dropna=False).agg(agg_dict)
    else:
        result = combined.drop_duplicates(subset=key_cols).reset_index(drop=True)

    # 6. 원본 컬럼 순서 복원
    orig_order = [c for c in dfs[0].columns if c in result.columns]
    result = result[orig_order]

    # 7. 소수점 없는 float → Int64
    for col in result.select_dtypes(include=["float64"]).columns:
        non_null = result[col].dropna()
        if len(non_null) and (non_null % 1 == 0).all():
            result[col] = result[col].astype("Int64")

    file_names = " + ".join(f["name"] for f in files_info[:3])
    if len(files_info) > 3:
        file_names += f" 외 {len(files_info) - 3}개"

    return {
        "type": "dataframe",
        "value": result,
        "label": "동일 양식 통합 결과",
        "summary": (
            f"{file_names} → {len(result):,}행 × {len(result.columns)}컬럼\n"
            f"기준 컬럼: {', '.join(key_cols)}"
            + (f" + 코드 컬럼: {', '.join(code_cols)}" if code_cols else "")
            + f" | 수치 {len(measure_cols)}개 평균, 텍스트 {len(text_cols)}개 first"
        ),
    }


# ── 내보내기 ──────────────────────────────────────────────────────────────────

def export_data(
    files_info: list[dict],
    last_result: "pd.DataFrame | None" = None,
    **kwargs,
) -> dict:
    """현재 데이터(last_result 우선, 없으면 첫 번째 파일)를 xlsx로 저장.

    Returns:
        {"type": "dataframe", "value": pd.DataFrame, "label": str, "saved_files": list}
    """
    import datetime
    from services.file_manager import RESULT_DIR
    from services.result_naming import export_filename

    df = last_result if isinstance(last_result, pd.DataFrame) else _load_df(files_info)
    if df is None:
        return {"type": "error", "message": "저장할 데이터가 없습니다."}

    prompt = kwargs.get("prompt", "")
    fname = export_filename(prompt=prompt)
    dest  = RESULT_DIR / fname
    df.to_excel(dest, index=False)

    return {
        "type": "dataframe",
        "value": df,
        "label": "저장 완료",
        "summary": f"{len(df):,}행 × {len(df.columns)}컬럼 → **{fname}** 저장 완료",
        "saved_files": [fname],
    }


# ── 필터 후 정렬 체이닝 ───────────────────────────────────────────────────────

def filter_then_sort(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """filter_rows → sort_rows 순으로 체이닝 실행.

    "값 1000 이상인 행을 수치 기준 내림차순 정렬" 같은 요청을 처리.
    """
    filter_res = filter_rows(files_info, prompt=prompt, **kwargs)
    if filter_res.get("type") == "error":
        return filter_res

    # filter 결과 DataFrame을 임시 files_info 형태로 래핑해 sort에 전달
    filtered_df: pd.DataFrame = filter_res["value"]

    # sort_rows는 files_info를 read_file로 읽으므로,
    # 여기서는 직접 DataFrame에 정렬 로직을 적용한다
    ascending = "오름차순" in prompt or "ascending" in prompt.lower()
    if "내림차순" in prompt or "descending" in prompt.lower():
        ascending = False

    sort_col = None
    for col in filtered_df.columns:
        if str(col).lower() in prompt.lower():
            sort_col = col
            break
    if sort_col is None:
        nums = [c for c in filtered_df.columns if pd.api.types.is_numeric_dtype(filtered_df[c])]
        sort_col = nums[0] if nums else filtered_df.columns[0]

    result = filtered_df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
    direction = "오름차순" if ascending else "내림차순"

    filter_summary = filter_res.get("summary", "")
    return {
        "type": "dataframe",
        "value": result,
        "label": "필터 + 정렬 결과",
        "summary": f"{filter_summary} → {sort_col} {direction} 정렬",
    }


def head_aggregate(
    files_info: list[dict],
    prompt: str = "",
    **kwargs,
) -> dict:
    """처음 N행의 수치 컬럼 합계를 파일별로 계산.

    "N행 뽑아서 합계내줘" 같은 요청을 LLM 없이 처리.
    """
    import re
    m = re.search(r"(\d+)\s*행", prompt)
    n = int(m.group(1)) if m else 5

    rows = []
    for entry in files_info:
        df = read_file(entry.get("name", ""), sheet_name=entry.get("sheet"))
        if df is None or df.empty:
            continue
        top_n = df.iloc[:n]
        num_cols = [c for c in top_n.columns if pd.api.types.is_numeric_dtype(top_n[c])]
        row: dict = {"파일명": entry.get("name", "")}
        for col in num_cols:
            row[col] = top_n[col].sum()
        rows.append(row)

    if not rows:
        return {"type": "error", "value": "처리할 파일이 없습니다."}

    result = pd.DataFrame(rows)
    return {
        "type": "dataframe",
        "value": result,
        "label": f"처음 {n}행 합계",
        "summary": f"{len(files_info)}개 파일 × 처음 {n}행 수치 컬럼 합계",
    }
