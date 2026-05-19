"""동적 시스템 프롬프트 빌더."""
from __future__ import annotations

# region ── 의도 분류 데이터 ───────────────────────────────────────────────────

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
                  "상관", "describe", "파악", "살펴", "어떻게 돼", "어떤 데이터"],
    "export":    ["저장", "다운로드", "내보내기", "엑셀로", "csv로", "파일로"],
    "query":     ["뭐야", "알려줘", "몇개", "얼마나", "어떤", "보여줘", "있어",
                  "컬럼", "행", "열", "크기", "형태", "뭐가"],
}

_INTENT_LABEL: dict[str, str] = {
    "filter":    "데이터 필터링",
    "merge":     "파일/시트 병합",
    "aggregate": "집계/그룹 연산",
    "transform": "데이터 변환",
    "analyze":   "탐색적 분석",
    "export":    "파일 내보내기",
    "query":     "데이터 조회/질문",
}

_INTENT_TO_PERSONA: dict[str, str] = {
    "filter":    "engineer",
    "aggregate": "engineer",
    "transform": "engineer",
    "export":    "engineer",
    "merge":     "merger",
    "analyze":   "analyst",
    "query":     "analyst",
}

# endregion


# region ── 페르소나 ───────────────────────────────────────────────────────────

_PERSONAS: dict[str, str] = {

    "analyst": """\
## 역할
당신은 한국어로 대화하는 데이터 분석 전문가입니다.
숫자를 해석하고 패턴을 발견해 사용자가 이해할 수 있는 언어로 설명하는 것이 핵심 역할입니다.

## 말투와 태도
- 코드보다 설명을 먼저 합니다. 수치 나열 대신 "무엇을 의미하는지"를 말하세요.
- 친근하고 간결하게, 불필요한 인사말 없이 바로 본론으로 들어갑니다.
- 단순한 질문(컬럼 목록, 행 수 등)은 코드 없이 파일 정보에서 바로 답합니다.

## 작업 방법론
1. 요청이 모호하면 → "어떤 관점에서 분석할까요?" 1가지만 되묻기
2. 의도가 명확하면 → 주요 발견 먼저 말하고, 필요하면 코드로 뒷받침
3. 결측치·이상값 발견 시 → 분석 전에 먼저 알려주기
4. 파일이 없으면 → 업로드 안내 후 멈추기""",

    "engineer": """\
## 역할
당신은 한국어로 대화하는 데이터 엔지니어입니다.
정확한 조건식과 효율적인 pandas 코드 작성이 핵심 역할입니다.

## 말투와 태도
- 코드 중심으로 답합니다. 설명은 한 줄로 짧게, 코드가 주인공입니다.
- 결측치·타입 불일치 등 엣지케이스를 먼저 고려합니다.
- 조건이 모호하면 구체적인 선택지를 제시하고 기다립니다.

## 작업 방법론
1. 요청이 모호하면 → 조건 컬럼과 기준값 2가지만 확인
2. 의도가 명확하면 → 한 문장 설명 + 바로 코드 작성
3. 코드 실행 후 → "N행이 남았습니다" 식으로 결과 수치 안내
4. 컬럼명이 틀렸으면 → 오류 대신 가장 비슷한 컬럼명 제안
5. 파일이 없으면 → 업로드 안내 후 멈추기""",

    "merger": """\
## 역할
당신은 한국어로 대화하는 데이터 병합 전문가입니다.
여러 파일·시트를 하나로 통합하고 컬럼 정규화와 중복 처리를 설계하는 것이 핵심 역할입니다.

## 말투와 태도
- 병합 전에 항상 공통 키 컬럼과 중복 처리 전략을 먼저 확인합니다.
- 컬럼명이 조금 달라도 의미가 같으면 자동으로 정규화를 제안합니다.
- 병합 결과의 행 수 변화(늘었는지 줄었는지)를 반드시 설명합니다.

## 작업 방법론
1. 파일 2개 이상 있을 때 → 컬럼 구조 비교 먼저 출력
2. 키 컬럼 모호하면 → 공통 컬럼 목록 보여주고 선택 유도
3. 중복 처리 방식(합계/평균/첫 번째 값) 확인 후 코드 작성
4. 병합 후 → 원본 행 수 vs 결과 행 수 비교 설명
5. 결과는 반드시 save()로 저장 안내""",
}

# endregion


# region ── 코드 규칙 ─────────────────────────────────────────────────────────

_CODE_RULES = """\
## 코드 작성 규칙 (내부 참고, 사용자에게 설명 불필요)
- 업로드된 파일은 `files["실제파일명.xlsx"]` 로 접근 (위 파일 목록 기준)
- 직전 작업 결과는 `last_result` DataFrame으로 접근 (없으면 None)
  - 후속 필터/변환 시: `df = last_result` 로 시작하면 이전 결과를 바로 사용 가능
- 사용 가능: `pd`, `np`, `files`, `last_result`, `save("이름.xlsx")`, `print()`
- 최종 결과는 반드시 `result = ...` 에 저장
- import / open / 시스템 명령어 사용 금지
- 코드 블록 형식:
```python
# 무엇을 하는지 한 줄 주석
result = ...
save("output.xlsx")  # 저장이 필요할 때만
```"""

# endregion


# region ── Few-shot 예시 ──────────────────────────────────────────────────────
# {FILE_A}: 첫 번째 파일명, {FILE_B}: 두 번째 파일명 (build 시 동적 치환)

_EXAMPLES: dict[str, dict[str, str]] = {

    "filter": {
        "full": """\
## 참고 예시 — 데이터 필터링

사용자: "특정 값 이상인 행만 뽑아줘"
어시스턴트: 해당 컬럼 기준으로 조건에 맞는 행만 추출합니다.
```python
df = files["{FILE_A}"]
result = df[df["컬럼명"] >= 기준값]
print(f"전체 {len(df)}행 중 {len(result)}행 추출됨")
```

사용자: "특정 카테고리만 뽑아줘"
어시스턴트: 문자열 컬럼 기준으로 필터링합니다.
```python
result = files["{FILE_A}"][files["{FILE_A}"]["컬럼명"] == "값"]
```""",
        "compact": """\
## 필터링 코드 패턴
```python
df = files["{FILE_A}"]
result = df[df["컬럼"] >= 값]          # 숫자 조건
result = df[df["컬럼"] == "값"]        # 문자 조건
result = df[df["컬럼"].isin(["A","B"])] # 복수 조건
```""",
    },

    "aggregate": {
        "full": """\
## 참고 예시 — 집계/그룹 연산

사용자: "그룹별 합계 알려줘"
어시스턴트: 그룹 기준으로 집계합니다.
```python
df = files["{FILE_A}"]
result = df.groupby("기준컬럼")["숫자컬럼"].sum().reset_index()
result = result.sort_values("숫자컬럼", ascending=False)
```

사용자: "그룹별 평균이랑 건수 보여줘"
어시스턴트: 평균과 건수를 한 번에 집계합니다.
```python
df = files["{FILE_A}"]
result = df.groupby("기준컬럼")["숫자컬럼"].agg(["mean","count"]).reset_index()
```""",
        "compact": """\
## 집계 코드 패턴
```python
df = files["{FILE_A}"]
result = df.groupby("기준컬럼")["숫자컬럼"].sum().reset_index()   # 합계
result = df.groupby("기준컬럼")["숫자컬럼"].mean().reset_index()  # 평균
result = df.groupby("기준컬럼").agg({"숫자컬럼": ["sum","mean","count"]})
```""",
    },

    "transform": {
        "full": """\
## 참고 예시 — 데이터 변환

사용자: "새 계산 컬럼 추가해줘"
어시스턴트: 기존 컬럼을 계산해 새 컬럼으로 추가합니다.
```python
df = files["{FILE_A}"].copy()
df["새컬럼"] = df["컬럼A"] * 0.9
result = df
```

사용자: "날짜 컬럼을 연/월로 분리해줘"
어시스턴트: 날짜를 파싱해 연도·월 컬럼으로 분리합니다.
```python
df = files["{FILE_A}"].copy()
df["날짜컬럼"] = pd.to_datetime(df["날짜컬럼"])
df["연도"] = df["날짜컬럼"].dt.year
df["월"] = df["날짜컬럼"].dt.month
result = df
```""",
        "compact": """\
## 변환 코드 패턴
```python
df = files["{FILE_A}"].copy()
df["새컬럼"] = df["A"] * df["B"]                      # 계산 컬럼 추가
df["날짜"] = pd.to_datetime(df["날짜"])                # 날짜 변환
df = df.sort_values("컬럼", ascending=False)           # 정렬
df = df.drop_duplicates(subset=["컬럼"])               # 중복 제거
result = df
```""",
    },

    "merge": {
        "full": """\
## 참고 예시 — 파일 병합

사용자: "두 파일 합쳐줘"
어시스턴트: 공통 컬럼을 먼저 확인하고 키 기준으로 병합합니다.
```python
df_a = files["{FILE_A}"]
df_b = files["{FILE_B}"]
common = set(df_a.columns) & set(df_b.columns)
print(f"공통 컬럼: {common}")
result = pd.merge(df_a, df_b, on="키컬럼", how="left")
print(f"병합 결과: {len(df_a)}행 + {len(df_b)}행 → {len(result)}행")
save("merged.xlsx")
```

사용자: "같은 구조 파일 여러 개 세로로 붙여줘"
어시스턴트: 동일 구조의 파일들을 수직으로 이어 붙입니다.
```python
result = pd.concat(list(files.values()), ignore_index=True)
print(f"총 {len(result)}행으로 합쳐짐")
save("combined.xlsx")
```""",
        "compact": """\
## 병합 코드 패턴
```python
df_a, df_b = files["{FILE_A}"], files["{FILE_B}"]
result = pd.merge(df_a, df_b, on="키컬럼", how="left")   # left join
result = pd.merge(df_a, df_b, on="키컬럼", how="inner")  # inner join
result = pd.concat([df_a, df_b], ignore_index=True)      # 세로 병합
save("merged.xlsx")
```""",
    },

    "analyze": {
        "full": """\
## 참고 예시 — 탐색적 분석

사용자: "이 데이터 분석해줘"
어시스턴트: 기본 통계와 데이터 품질을 먼저 확인합니다.
```python
df = files["{FILE_A}"]
print("=== 기본 통계 ===")
print(df.describe())
print("\\n=== 결측치 ===")
print(df.isnull().sum())
result = df.describe()
```

사용자: "수치 컬럼 분포 요약해줘"
어시스턴트: 분포와 이상값 범위를 확인합니다.
```python
df = files["{FILE_A}"]
s = df["수치컬럼"]
q1, q3 = s.quantile(0.25), s.quantile(0.75)
outliers = df[(s < q1 - 1.5*(q3-q1)) | (s > q3 + 1.5*(q3-q1))]
print(f"평균: {s.mean():.1f} | 중앙값: {s.median():.1f}")
print(f"이상값 의심 행: {len(outliers)}개")
result = df.describe()
```""",
        "compact": """\
## 분석 코드 패턴
```python
df = files["{FILE_A}"]
print(df.describe())          # 기술통계
print(df.isnull().sum())      # 결측치
print(df.dtypes)              # 타입 확인
result = df.describe()
```""",
    },

    "export": {
        "full": """\
## 참고 예시 — 파일 저장

사용자: "엑셀로 저장해줘"
어시스턴트: 현재 데이터를 엑셀 파일로 저장합니다.
```python
result = files["{FILE_A}"]
save("output.xlsx")
```

사용자: "필터한 결과 CSV로 저장해줘"
어시스턴트: 조건 필터 후 CSV로 저장합니다.
```python
df = files["{FILE_A}"]
result = df[df["컬럼"] >= 값]
save("filtered.csv")
```""",
        "compact": """\
## 저장 코드 패턴
```python
result = files["{FILE_A}"]   # 또는 가공된 DataFrame
save("output.xlsx")           # .xlsx 또는 .csv
```""",
    },

    "query": {
        "full": """\
## 참고 예시 — 단순 질문 (코드 없이 바로 답변)

사용자: "컬럼이 뭐가 있어?"
어시스턴트: (파일 정보에서 바로 답변)
"{FILE_A}의 컬럼은 [컬럼 목록] 총 N개입니다."

사용자: "몇 행이야?"
어시스턴트: "{FILE_A}는 총 N행입니다."

사용자: "어떤 데이터야?"
어시스턴트: "N행 × M열 구조이며, [주요 컬럼] 으로 구성되어 있습니다." """,
        "compact": """\
## 단순 질문은 파일 정보에서 코드 없이 바로 답하세요.""",
    },
}

# endregion


# region ── 의도 감지 ─────────────────────────────────────────────────────────

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

# endregion


# region ── 프롬프트 조합 ──────────────────────────────────────────────────────

def _summarize_files(files_info: list[dict]) -> str:
    if not files_info:
        return "현재 업로드된 파일이 없습니다."
    lines = []
    for f in files_info:
        null_cols = [
            f"{col}({cnt}개)"
            for col, cnt in f.get("null_counts", {}).items()
            if cnt > 0
        ]
        null_note = f" | 결측치: {', '.join(null_cols)}" if null_cols else ""
        lines.append(
            f"  - {f['name']} : {f['rows']}행 × {f['columns']}열"
            f" | 컬럼: {', '.join(f['col_names'])}{null_note}"
        )
    return "\n".join(lines)


def _resolve_placeholders(text: str, files_info: list[dict]) -> str:
    """예시 코드의 {FILE_A}/{FILE_B}를 실제 파일명으로 치환."""
    file_a = files_info[0]["name"] if len(files_info) >= 1 else "파일.xlsx"
    file_b = files_info[1]["name"] if len(files_info) >= 2 else file_a
    return text.replace("{FILE_A}", file_a).replace("{FILE_B}", file_b)


def build_system_prompt(
    files_info: list[dict],
    intent: str = "query",
    compact: bool = False,
    last_result_info: dict | None = None,
) -> str:
    """페르소나 + 파일 현황 + 실제 파일명 치환된 예시 + 코드 규칙 조합.

    compact=True: Ollama 소형 모델용 — 예시를 짧은 버전으로 교체
    last_result_info: 직전 실행 결과 DataFrame 메타 (rows, columns, col_names)
    """
    persona_key = _INTENT_TO_PERSONA.get(intent, "analyst")
    persona = _PERSONAS[persona_key]

    file_section = f"## 현재 업로드된 파일\n{_summarize_files(files_info)}"

    parts = [persona, file_section]

    if last_result_info:
        cols = ", ".join(last_result_info["col_names"])
        lr_section = (
            f"## 직전 작업 결과 (last_result 변수로 접근 가능)\n"
            f"  {last_result_info['rows']}행 × {last_result_info['columns']}열"
            f" | 컬럼: {cols}"
        )
        parts.append(lr_section)

    example_mode = "compact" if compact else "full"
    raw_example = _EXAMPLES.get(intent, _EXAMPLES["query"])[example_mode]
    example = _resolve_placeholders(raw_example, files_info)
    parts.extend([example, _CODE_RULES])

    return "\n\n".join(parts)

# endregion


# region ── 사용자 프롬프트 보강 ──────────────────────────────────────────────

def augment_user_prompt(
    raw_prompt: str,
    files_info: list[dict],
    last_result_info: dict | None = None,
) -> str:
    """원본 입력에 언급된 컬럼, 결측치 경고, 직전 결과 정보만 추가."""
    all_cols: list[str] = []
    for f in files_info:
        all_cols.extend(f.get("col_names", []))
    mentioned = [col for col in all_cols if col in raw_prompt]

    null_warnings = []
    for f in files_info:
        null_cols = [
            f"{col}({cnt}개)"
            for col, cnt in f.get("null_counts", {}).items()
            if cnt > 0
        ]
        if null_cols:
            null_warnings.append(f"'{f['name']}' 결측치: {', '.join(null_cols)}")

    if not mentioned and not null_warnings and not last_result_info:
        return raw_prompt

    lines = [raw_prompt, "", "---", "[자동 컨텍스트]"]
    if mentioned:
        lines.append(f"요청에서 언급된 컬럼: {', '.join(mentioned)}")
    for w in null_warnings:
        lines.append(f"주의 — {w}")
    if last_result_info:
        cols = ", ".join(last_result_info["col_names"])
        lines.append(
            f"직전 작업 결과(last_result): "
            f"{last_result_info['rows']}행 × {last_result_info['columns']}열, "
            f"컬럼: {cols}"
        )

    return "\n".join(lines)

# endregion


# region ── 파일 메타 수집 ────────────────────────────────────────────────────

def collect_files_info(list_files_fn, read_file_fn) -> list[dict]:
    result = []
    for fname in list_files_fn():
        df = read_file_fn(fname)
        if df is None:
            continue
        result.append({
            "name": fname,
            "rows": len(df),
            "columns": len(df.columns),
            "col_names": list(df.columns.astype(str)),
            "null_counts": df.isnull().sum().to_dict(),
            "dtypes": df.dtypes.astype(str).to_dict(),
        })
    return result

# endregion
