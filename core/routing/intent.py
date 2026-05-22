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

INTENT_LABEL: dict[str, str] = {
    "filter":    "데이터 필터링",
    "merge":     "파일/시트 병합",
    "aggregate": "집계/그룹 연산",
    "transform": "데이터 변환",
    "analyze":   "탐색적 분석",
    "export":    "파일 내보내기",
    "query":     "데이터 조회/질문",
}

# 내부 전용 — builder.py에서만 사용
_INTENT_TO_PERSONA: dict[str, str] = {
    "filter":    "engineer",
    "aggregate": "engineer",
    "transform": "engineer",
    "export":    "engineer",
    "merge":     "merger",
    "analyze":   "analyst",
    "query":     "analyst",
}


def detect_intent(prompt: str) -> str:
    """사용자 입력에서 의도를 분류. 동점 시 순서 우선."""
    lower = prompt.lower()
    scores: dict[str, int] = {intent: 0 for intent in _INTENT_MAP}
    for intent, keywords in _INTENT_MAP.items():
        for kw in keywords:
            if kw in lower:
                scores[intent] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "query"
