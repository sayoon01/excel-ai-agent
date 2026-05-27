"""의도 분류 데이터 및 detect_intent."""
from __future__ import annotations

_INTENT_MAP: dict[str, list[str]] = {
    "filter":    ["필터", "뽑아", "추출", "조건", "이상", "이하", "초과", "미만",
                  "포함", "제외", "where", "해당", "특정", "걸러"],
    "merge":     ["병합", "합쳐", "통합", "결합", "join", "합산", "묶어", "연결",
                  "붙여", "이어"],
    "aggregate": ["합계", "평균", "최대", "최소", "집계", "group", "그룹", "카운트",
                  "개수", "총합", "mean", "sum", "max", "min", "몇개씩", "별로"],
    "transform": ["변환", "바꿔", "수정", "추가", "삭제", "정렬", "rename",
                  "컬럼 추가", "열 추가", "파생", "계산", "나눠", "곱해", "새 컬럼"],
    "analyze":   ["분석", "통계", "요약", "insight", "패턴", "트렌드", "분포",
                  "상관", "describe", "파악", "살펴", "어떻게 돼", "어떤 데이터",
                  "차트", "그래프", "시각화", "그려줘", "막대", "선 그래프", "파이"],
    "export":    ["저장", "다운로드", "내보내기", "엑셀로", "csv로", "파일로"],
    "query":     ["뭐야", "알려줘", "몇개", "얼마나", "어떤", "보여줘", "있어",
                  "컬럼", "행", "열", "크기", "형태", "뭐가"],
}

# merge 세부 분류 — 수직 concat vs 수평 join
_MERGE_UNION_HINTS: list[str] = [
    "세로로", "쌓아", "이어붙여", "concat",
    "같은 형식", "같은 구조", "같은 양식", "동일 양식", "동일 형식", "동일 구조",
    "1월", "2월", "3월", "4월", "5월", "6월",
    "7월", "8월", "9월", "10월", "11월", "12월",
    "상반기", "하반기", "1분기", "2분기", "3분기", "4분기",
    "월별", "분기별", "연도별", "지역별", "부서별",
]
_MERGE_JOIN_HINTS: list[str] = [
    "기준으로 합쳐", "키 기준", "키 컬럼으로", "키컬럼",
    "조인", "join", "에 붙여줘", "에 연결", "에 매핑", "매핑",
    "사번", "고객id", "고객번호", "상품코드", "거래처코드", "주문번호",
]

INTENT_LABEL: dict[str, str] = {
    "filter":       "데이터 필터링",
    "merge":        "파일/시트 병합",
    "merge_union":  "수직 통합 (concat)",
    "merge_join":   "수평 결합 (join)",
    "aggregate":    "집계/그룹 연산",
    "transform":    "데이터 변환",
    "analyze":      "탐색적 분석",
    "export":       "파일 내보내기",
    "query":        "데이터 조회/질문",
}

# 내부 전용 — builder.py에서만 사용
_INTENT_TO_PERSONA: dict[str, str] = {
    "filter":       "engineer",
    "aggregate":    "engineer",
    "transform":    "engineer",
    "export":       "engineer",
    "merge":        "merger",
    "merge_union":  "merger",
    "merge_join":   "merger",
    "analyze":      "analyst",
    "query":        "analyst",
}


def detect_merge_subtype(prompt: str) -> str:
    """'merge' 의도를 수직(union) / 수평(join) / 모호(merge)로 세분화."""
    union_score = sum(1 for h in _MERGE_UNION_HINTS if h in prompt)
    join_score  = sum(1 for h in _MERGE_JOIN_HINTS  if h in prompt)
    if union_score > join_score:
        return "merge_union"
    if join_score > union_score:
        return "merge_join"
    return "merge"


def detect_intent(prompt: str) -> str:
    """사용자 입력에서 의도를 분류. 동점 시 순서 우선."""
    lower = prompt.lower()
    scores: dict[str, int] = {intent: 0 for intent in _INTENT_MAP}
    for intent, keywords in _INTENT_MAP.items():
        for kw in keywords:
            if kw in lower:
                scores[intent] += 1

    # merge 세부 힌트 — merge 키워드가 없을 때만 최소 1점 부여 (이중 누적 방지)
    # "조인/사번" 등 _INTENT_MAP에 없는 표현도 감지하되, 이미 merge 점수가 있으면 추가 가산 안 함
    union_hits = sum(1 for h in _MERGE_UNION_HINTS if h in lower)
    join_hits  = sum(1 for h in _MERGE_JOIN_HINTS  if h in lower)
    if scores["merge"] == 0 and (union_hits + join_hits) > 0:
        scores["merge"] = 1

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "query"
    if best == "merge":
        return detect_merge_subtype(lower)
    return best
