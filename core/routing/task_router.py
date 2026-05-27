"""
Task 분류기 — 사용자 요청을 분석해 실행 모드와 옵션을 결정한다.

3단계 분류:
  1차 rule_classify   : 키워드 기반, 빠름 (confidence >= 0.8이면 바로 반환)
  2차 llm_classify    : LLM JSON 분류, 정확 (애매한 경우에만 호출)
  3차 code fallback   : confidence < 0.6이면 code 모드로 안전하게 처리
"""
from __future__ import annotations

# ── Rule 기반 분류 테이블 ────────────────────────────────────────────────────
# (키워드 목록, tool 이름 또는 None, mode, confidence)

_TOOL_RULES: list[tuple[list[str], str, float]] = [
    # 파일 정보 조회
    (["몇 행", "행 수", "행수", "몇개", "몇 개", "개수"],       "get_row_count",   0.97),
    (["결측치", "빈칸", "누락", "missing", "null"],              "analyze_missing", 0.95),
    (["컬럼", "열", "column"],                                   "get_profile",     0.85),

    # 동일 양식 통합 — 집계보다 먼저 검사 (항목별 평균이 aggregate_data와 충돌 방지)
    (["동일 양식", "같은 양식", "같은 형식", "같은 구조",
      "항목별 평균", "항목 기준 평균",
      "세로로 합치", "세로로 합쳐", "세로로 쌓",
      "세로 병합", "세로로 통합", "세로로 합산"],               "merge_same_format", 0.94),
    (["파일 통합", "파일들 통합", "하나로 통합",
      "통합해", "통합해줘", "통합하고", "통합한 후"],            "merge_same_format", 0.85),

    # 집계
    (["합계", "총합", "sum", "총액"],                            "aggregate_data",  0.92),
    (["평균", "mean", "avg", "평균값"],                          "aggregate_data",  0.92),
    (["최대", "최소", "max", "min", "최댓값", "최솟값"],         "aggregate_data",  0.90),

    # 필터 + 정렬 체이닝 (단독 필터·정렬보다 먼저 검사)
    (["필터 후 정렬", "추출 후 정렬", "뽑아서 정렬", "조건 후 정렬",
      "이상인.*정렬", "이하인.*정렬", "보다 큰.*정렬"],                        "filter_then_sort", 0.90),

    # 필터 / 정렬
    (["필터", "추출", "뽑아", "조건"],                                         "filter_rows", 0.88),
    (["상위", "하위", "top", "bottom", "이상인", "이하인", "초과인", "미만인",
      "보다 큰", "보다 작은", "포함된", "제외된", "결측 제거", "빈칸 제거"],    "filter_rows", 0.86),
    (["정렬", "순서", "내림차순", "오름차순", "sort"],                          "sort_rows",   0.90),

    # 일반 병합 (스키마 다른 파일 join/concat)
    (["병합", "합치", "조인", "merge", "join"],                  "merge_files",     0.90),

    # 저장 / 내보내기
    (["저장", "다운로드", "내보내기", "export", "엑셀로", "파일로"], "export_data",  0.88),

    # 차트 (tool 이름 없음 → needs_chart=True 로만 처리)
    (["막대", "bar", "바차트"],                                      "create_chart", 0.88),
    (["파이", "pie", "원형"],                                        "create_chart", 0.88),
    (["선", "line", "라인", "추이"],                                 "create_chart", 0.82),
    (["산점도", "scatter", "상관관계"],                              "create_chart", 0.88),
    (["히스토그램", "histogram", "분포도", "빈도분포"],              "create_chart", 0.88),
    (["박스플롯", "boxplot", "box plot", "사분위", "분위수"],        "create_chart", 0.88),
    (["차트", "그래프", "시각화", "plot"],                           "create_chart", 0.80),
]

_LLM_RULES: list[tuple[list[str], float]] = [
    (["뭐야", "뭔가요", "뭐예요", "뭐에요"], 0.95),
    (["알려줘", "알려주세요"],               0.90),
    (["설명", "설명해", "설명해줘"],         0.90),
    (["왜", "이유", "원인"],                 0.85),
    (["어떻게 생각", "의견"],               0.85),
    (["의미", "뜻", "차이"],                0.88),
]

_CODE_RULES: list[tuple[list[str], float]] = [
    (["분석", "분석해"],                                        0.75),
    (["비교", "대비"],                                          0.75),
    (["패턴", "추이 분석", "상관"],                             0.80),
    (["이면서", "동시에", "그리고", "또한"],                    0.78),
    (["단계별", "여러 조건", "복합"],                           0.82),
]

# 복잡도 힌트 — llm으로 분류됐어도 code로 격상
_COMPLEXITY_HINTS = ["이면서", "동시에", "비교", "상관", "단계별", "여러", "복합", "원인"]

# chart / summary / export 힌트
_CHART_HINTS   = [
    "차트", "그래프", "시각화", "plot",
    "막대", "파이", "선", "bar", "pie", "line",
    "산점도", "scatter", "히스토그램", "histogram", "분포도",
    "박스플롯", "boxplot", "사분위", "분위수",
]
_SUMMARY_HINTS = ["요약", "정리", "설명", "해석", "총평", "인사이트"]
_EXPORT_HINTS  = ["저장", "다운로드", "내보내기", "export", "엑셀로", "파일로"]

# 이전 결과 참조 키워드 — "방금 결과에서 합계" 같은 체이닝 감지
_PREV_KW = {
    "방금", "이전 결과", "그 결과", "마지막 결과",
    "앞의 결과", "위의 결과", "저번 결과",
    "필터한 결과", "정렬한 결과", "집계한 결과",
    "그 데이터", "그것에서", "그거에서",
}


def _detect_options(prompt: str) -> dict:
    """needs_chart / needs_summary / needs_export / use_last_result 감지."""
    return {
        "needs_chart":     any(h in prompt for h in _CHART_HINTS),
        "needs_summary":   any(h in prompt for h in _SUMMARY_HINTS),
        "needs_export":    any(h in prompt for h in _EXPORT_HINTS),
        "use_last_result": any(k in prompt for k in _PREV_KW),
    }


_FILTER_KW = {"필터", "추출", "뽑아", "조건", "상위", "하위",
              "이상인", "이상", "이하인", "이하", "초과인", "초과", "미만인", "미만",
              "보다 큰", "보다 작은", "포함된", "포함", "제외된", "제외", "결측 제거"}
_SORT_KW   = {"정렬", "순서", "내림차순", "오름차순", "sort"}


def _rule_classify(prompt: str, intent: str) -> dict:
    """1차 rule 기반 분류."""
    options = _detect_options(prompt)

    # ── intent 선행 라우팅 — 키워드 루프보다 먼저 처리 ────────────────────────
    # intent.py가 이미 merge 세부 분류를 완료한 경우, 키워드 룰이 덮어쓰지 못하게 막음
    if intent == "merge_union":
        return {"mode": "tool", "tool": "merge_same_format", "confidence": 0.88, **options}
    if intent == "merge_join":
        return {"mode": "code", "tool": None, "confidence": 0.80, **options}

    # ── 복합 조건 체크 (단일 키워드 루프보다 반드시 먼저 실행) ──────────────────

    # 차트 키워드 + 컬럼 키워드가 동시에 있으면 chart 우선 (get_profile 충돌 방지)
    _CHART_KW = {
        "차트", "그래프", "시각화", "plot",
        "막대", "파이", "선", "bar", "pie", "line",
        "산점도", "scatter", "히스토그램", "histogram", "분포도",
        "박스플롯", "boxplot", "사분위", "분위수",
    }
    _COL_KW   = {"컬럼", "열", "column"}
    if any(k in prompt for k in _CHART_KW) and any(k in prompt for k in _COL_KW):
        return {"mode": "tool", "tool": "create_chart", "confidence": 0.86, **options}

    # 통합/병합 + 평균 동시 → merge_same_format (aggregate_data 0.92보다 높게)
    # "파일 통합 + 동일 표 항목 평균", "합쳐서 평균값으로" 같은 복합 요청 처리
    _MERGE_KW = {"통합", "병합", "합치", "합쳐", "합산", "붙여", "모아"}
    _AVG_KW   = {"평균", "평균값", "항목 평균", "동일 표", "항목별", "항목 기준", "mean", "avg"}
    if any(k in prompt for k in _MERGE_KW) and any(k in prompt for k in _AVG_KW):
        return {"mode": "tool", "tool": "merge_same_format", "confidence": 0.96, **options}

    # 체이닝 먼저 감지 — filter 키워드 + sort 키워드가 동시에 있으면 filter_then_sort
    if any(k in prompt for k in _FILTER_KW) and any(k in prompt for k in _SORT_KW):
        return {"mode": "tool", "tool": "filter_then_sort", "confidence": 0.90, **options}

    # "N행 뽑아서 합계" → head_aggregate tool (LLM 불필요, 전 파일 처리)
    import re as _re
    if (_re.search(r"\d+\s*행", prompt)
            and any(k in prompt for k in {"뽑아", "추출"})
            and any(k in prompt for k in {"합계", "총합", "sum"})):
        return {"mode": "tool", "tool": "head_aggregate", "confidence": 0.95, **options}

    # 필터 + 집계 복합 요청 → code 모드 (LLM이 순서대로 처리)
    # "뽑아서 합계", "추출 후 평균" 같은 2단계 요청은 단일 tool로 처리 불가
    _AGG_KW2 = {"합계", "평균", "최대", "최소", "집계", "sum", "mean", "max", "min", "총합"}
    _FILTER_KW2 = {"뽑아", "추출", "필터", "조건"}
    if any(k in prompt for k in _AGG_KW2) and any(k in prompt for k in _FILTER_KW2):
        return {"mode": "code", "tool": None, "confidence": 0.82, **options}

    # tool 모드 먼저 검사 — tool 키워드가 있으면 llm/query 키워드보다 우선
    best_tool, best_conf = None, 0.0
    for keywords, tool_name, conf in _TOOL_RULES:
        if any(k in prompt for k in keywords):
            if conf > best_conf:
                best_tool, best_conf = tool_name, conf

    if best_tool and best_conf >= 0.8:
        return {"mode": "tool", "tool": best_tool, "confidence": best_conf, **options}

    # llm 모드 검사 (tool 키워드 없는 경우에만)
    for keywords, conf in _LLM_RULES:
        if any(k in prompt for k in keywords):
            if not any(h in prompt for h in _COMPLEXITY_HINTS):
                return {"mode": "llm", "tool": None, "confidence": conf, **options}

    # code 모드 검사
    for keywords, conf in _CODE_RULES:
        if any(k in prompt for k in keywords):
            return {"mode": "code", "tool": None, "confidence": conf, **options}

    # intent 기반 기본값
    _intent_defaults = {
        "query":        ("llm",  0.60),
        "analyze":      ("code", 0.65),
        "filter":       ("tool", 0.70),
        "aggregate":    ("tool", 0.70),
        "transform":    ("code", 0.65),
        "merge":        ("tool", 0.70),
        "merge_union":  ("tool", 0.80),  # 동일 구조 수직 통합 → merge_same_format
        "merge_join":   ("code", 0.75),  # 키 기반 수평 결합 → LLM 코드 생성
        "export":       ("tool", 0.75),
    }
    mode, conf = _intent_defaults.get(intent, ("code", 0.55))
    # merge_union은 merge_same_format 도구로 직접 라우팅
    tool = "merge_same_format" if intent == "merge_union" else None
    return {"mode": mode, "tool": tool, "confidence": conf, **options}


def _llm_classify(prompt: str, intent: str, client=None) -> dict:
    """
    2차 LLM 기반 분류.
    client가 None이면 rule 결과에 confidence만 낮춰서 반환.
    """
    if client is None:
        base = _rule_classify(prompt, intent)
        base["confidence"] = max(base["confidence"] - 0.15, 0.4)
        return base

    options = _detect_options(prompt)
    system = (
        "사용자 요청을 분석해 아래 JSON 형식으로만 반환하세요. 설명 불필요.\n"
        '{"mode":"tool"|"code"|"llm", "tool":"함수명"|null, '
        '"needs_chart":bool, "needs_summary":bool, "needs_export":bool, '
        '"confidence":0.0~1.0}\n\n'
        "mode 기준:\n"
        "  tool: 행수/결측치/합계/평균/필터/정렬/병합/차트 등 정형 작업\n"
        "  code: 복잡한 조건 분석, 다단계 변환, 비교/추이 분석\n"
        "  llm : 설명/해석/질문 (데이터 처리 불필요)\n"
        "tool 함수명: get_row_count, analyze_missing, get_profile, "
        "aggregate_data, filter_rows, sort_rows, merge_files, create_chart, null"
    )
    try:
        import json, re
        messages = [{"role": "user", "content": f"요청: {prompt}\nintent: {intent}"}]
        raw = "".join(client.chat_stream(messages, system))
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            result = json.loads(match.group())
            result.setdefault("tool", None)
            result.setdefault("confidence", 0.7)
            for k in ("needs_chart", "needs_summary", "needs_export"):
                result.setdefault(k, options[k])
            return result
    except Exception:
        pass

    base = _rule_classify(prompt, intent)
    base["confidence"] = 0.55
    return base


def classify_task(prompt: str, intent: str, client=None) -> dict:
    """
    3단계 task 분류.

    Returns:
        {
            "mode": "llm" | "tool" | "code",
            "tool": str | None,
            "needs_chart": bool,
            "needs_summary": bool,
            "needs_export": bool,
            "confidence": float,
        }
    """
    # 1차: rule
    task = _rule_classify(prompt, intent)

    if task["confidence"] >= 0.8:
        return task                         # 확실 → 바로 반환

    # 2차: LLM
    task = _llm_classify(prompt, intent, client)

    if task["confidence"] < 0.6:           # 불확실 → code fallback
        return {
            "mode": "code",
            "tool": None,
            "needs_chart":    task.get("needs_chart", False),
            "needs_summary":  task.get("needs_summary", False),
            "needs_export":   task.get("needs_export", False),
            "needs_approval": True,        # 분류 불확실 → Approval panel 강제 표시
            "confidence":     task["confidence"],
        }

    return task
