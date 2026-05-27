"""Intent별 few-shot 예시.

EXAMPLE_CORPUS  — RAG 검색 대상. 개별 Entry로 분리되어 있음.
EXAMPLES        — 정적 fallback용 기존 딕셔너리 (하위 호환 유지).
{FILE_A}/{FILE_B}는 builder에서 실제 파일명으로 치환된다.
"""

# ── RAG 검색 corpus ──────────────────────────────────────────────────────────
# query 필드가 임베딩 대상. template은 {FILE_A}/{FILE_B} placeholder 포함 코드.

EXAMPLE_CORPUS: list[dict] = [

    # ── filter ────────────────────────────────────────────────────────────────
    {
        "id": "filter_numeric",
        "intent": "filter",
        "query": "특정 값 이상인 행만 뽑아줘",
        "tags": ["숫자조건", "이상", "이하", "임계값"],
        "template": """\
df = files["{FILE_A}"]
result = df[df["컬럼명"] >= 0]  # 0 → 사용자가 요청한 실제 기준값으로 교체
print(f"전체 {len(df)}행 중 {len(result)}행 추출됨")""",
        "source": "builtin",
    },
    {
        "id": "filter_string",
        "intent": "filter",
        "query": "특정 카테고리만 뽑아줘",
        "tags": ["문자조건", "카테고리", "isin"],
        "template": 'result = files["{FILE_A}"][files["{FILE_A}"]["컬럼명"] == "값"]',
        "source": "builtin",
    },
    {
        "id": "filter_isin",
        "intent": "filter",
        "query": "여러 값 중 하나에 해당하는 행만 뽑아줘",
        "tags": ["isin", "복수조건", "목록필터"],
        "template": """\
df = files["{FILE_A}"]
result = df[df["컬럼명"].isin(["값A", "값B", "값C"])]""",
        "source": "builtin",
    },

    # ── aggregate ─────────────────────────────────────────────────────────────
    {
        "id": "aggregate_groupby_sum",
        "intent": "aggregate",
        "query": "그룹별 합계 알려줘",
        "tags": ["그룹", "합계", "groupby", "sum"],
        "template": """\
df = files["{FILE_A}"]
result = df.groupby("기준컬럼")["숫자컬럼"].sum().reset_index()
result = result.sort_values("숫자컬럼", ascending=False)""",
        "source": "builtin",
    },
    {
        "id": "aggregate_groupby_agg",
        "intent": "aggregate",
        "query": "그룹별 평균이랑 건수 보여줘",
        "tags": ["그룹", "평균", "건수", "agg"],
        "template": """\
df = files["{FILE_A}"]
result = df.groupby("기준컬럼")["숫자컬럼"].agg(["mean", "count"]).reset_index()""",
        "source": "builtin",
    },
    {
        "id": "aggregate_total_number",
        "intent": "aggregate",
        "query": "총 합계가 얼마야?",
        "tags": ["전체합계", "단일숫자", "number"],
        "template": """\
df = files["{FILE_A}"]
total = int(df["숫자컬럼"].sum())
print(f"총합: {total:,}")
result = {"type": "number", "value": total}""",
        "source": "builtin",
    },

    # ── transform ─────────────────────────────────────────────────────────────
    {
        "id": "transform_calc_col",
        "intent": "transform",
        "query": "새 계산 컬럼 추가해줘",
        "tags": ["파생컬럼", "계산", "추가"],
        "template": """\
df = files["{FILE_A}"].copy()
df["새컬럼"] = df["컬럼A"] * 0.9
result = df""",
        "source": "builtin",
    },
    {
        "id": "transform_date_split",
        "intent": "transform",
        "query": "날짜 컬럼을 연/월로 분리해줘",
        "tags": ["날짜", "연도", "월", "datetime"],
        "template": """\
df = files["{FILE_A}"].copy()
df["날짜컬럼"] = pd.to_datetime(df["날짜컬럼"])
df["연도"] = df["날짜컬럼"].dt.year
df["월"] = df["날짜컬럼"].dt.month
result = df""",
        "source": "builtin",
    },

    # ── merge ─────────────────────────────────────────────────────────────────
    {
        "id": "merge_join_key",
        "intent": "merge_join",
        "query": "파일들 키 기준으로 합쳐줘",
        "tags": ["join", "merge", "키컬럼", "left join"],
        "template": """\
dfs = list(files.values())

key_candidates = set(dfs[0].select_dtypes(exclude="number").columns)
for df in dfs[1:]:
    key_candidates &= set(df.select_dtypes(exclude="number").columns)
key_col = list(key_candidates)[0] if key_candidates else None
print(f"키 컬럼: {key_col}")

result = reduce(lambda left, right: pd.merge(left, right, on=key_col, how="left"), dfs)
print(f"병합 결과: {len(result)}행 × {len(result.columns)}열")""",
        "source": "builtin",
    },
    {
        "id": "merge_concat_vertical",
        "intent": "merge_union",
        "query": "같은 구조 파일 여러 개 세로로 붙여줘",
        "tags": ["concat", "세로합치기", "동일구조", "행추가"],
        "template": """\
result = pd.concat(list(files.values()), ignore_index=True)
print(f"총 {len(result)}행으로 합쳐짐")""",
        "source": "builtin",
    },

    # ── analyze ───────────────────────────────────────────────────────────────
    {
        "id": "analyze_basic",
        "intent": "analyze",
        "query": "이 데이터 분석해줘",
        "tags": ["기본분석", "결측치", "수치형", "요약"],
        "template": """\
df = files["{FILE_A}"]

missing = df.isnull().sum()
missing = missing[missing > 0]
for col, cnt in missing.items():
    print(f"  {col}: {cnt}개")

num_cols = df.select_dtypes(include="number").columns.tolist()
print(f"수치형 컬럼: {num_cols}")

result = pd.DataFrame({
    "항목": ["전체 행수", "전체 열수", "결측치 있는 컬럼 수", "수치형 컬럼 수"],
    "값": [len(df), len(df.columns), len(missing), len(num_cols)],
})""",
        "source": "builtin",
    },
    {
        "id": "analyze_distribution",
        "intent": "analyze",
        "query": "수치 컬럼 분포 요약해줘",
        "tags": ["분포", "IQR", "이상값", "평균", "중앙값"],
        "template": """\
df = files["{FILE_A}"]
rows = []
for col in df.select_dtypes(include="number").columns:
    s = df[col].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    outlier_cnt = int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())
    rows.append({
        "컬럼": col,
        "평균": round(s.mean(), 1),
        "중앙값": round(s.median(), 1),
        "이상값_의심": outlier_cnt,
    })
result = pd.DataFrame(rows)""",
        "source": "builtin",
    },
    {
        "id": "analyze_bar_chart",
        "intent": "analyze",
        "query": "막대 차트 그려줘",
        "tags": ["막대차트", "bar", "시각화", "chart"],
        "template": """\
df = files["{FILE_A}"]
cat_cols = df.select_dtypes(exclude="number").columns.tolist()
num_cols = df.select_dtypes(include="number").columns.tolist()
cat_col = cat_cols[0] if cat_cols else df.columns[0]
num_col = num_cols[0] if num_cols else df.columns[-1]
fig, ax = plt.subplots(figsize=(10, 5))
df.groupby(cat_col)[num_col].sum().plot(kind="bar", ax=ax, color="steelblue")
ax.set_title(f"{cat_col}별 {num_col} 합계")
ax.set_xlabel("")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
result = {"type": "plot", "value": fig}""",
        "source": "builtin",
    },
    {
        "id": "analyze_line_chart",
        "intent": "analyze",
        "query": "선 그래프로 추세 보여줘",
        "tags": ["선그래프", "line", "추세", "시계열"],
        "template": """\
df = files["{FILE_A}"]
num_cols = df.select_dtypes(include="number").columns.tolist()
num_col = num_cols[0] if num_cols else df.columns[-1]
fig, ax = plt.subplots(figsize=(10, 4))
df[num_col].plot(ax=ax, marker="o")
ax.set_title(f"{num_col} 추세")
plt.tight_layout()
result = {"type": "plot", "value": fig}""",
        "source": "builtin",
    },
    {
        "id": "analyze_multi_file",
        "intent": "analyze",
        "query": "파일들 비교 분석해줘",
        "tags": ["다중파일", "비교", "공통컬럼"],
        "template": """\
rows = []
for name, df in files.items():
    missing = df.isnull().sum()
    rows.append({
        "파일명": name,
        "행수": len(df),
        "열수": len(df.columns),
        "결측치_컬럼수": int((missing > 0).sum()),
        "수치형_컬럼수": len(df.select_dtypes(include="number").columns),
    })
result = pd.DataFrame(rows)

names = list(files.keys())
if len(names) >= 2:
    common = set(files[names[0]].columns) & set(files[names[1]].columns)
    print(f"공통 컬럼 {len(common)}개: {', '.join(sorted(common))}")""",
        "source": "builtin",
    },

    # ── export ────────────────────────────────────────────────────────────────
    {
        "id": "export_excel",
        "intent": "export",
        "query": "엑셀로 저장해줘",
        "tags": ["저장", "xlsx", "엑셀"],
        "template": """\
result = files["{FILE_A}"]
save("output.xlsx")""",
        "source": "builtin",
    },
    {
        "id": "export_csv_filtered",
        "intent": "export",
        "query": "필터한 결과 CSV로 저장해줘",
        "tags": ["저장", "csv", "필터후저장"],
        "template": """\
df = files["{FILE_A}"]
result = df[df["컬럼"] >= 0]  # 0 → 사용자가 요청한 실제 기준값으로 교체
save("filtered.csv")""",
        "source": "builtin",
    },

    # ── query ─────────────────────────────────────────────────────────────────
    {
        "id": "query_missing_count",
        "intent": "query",
        "query": "결측치 몇 개야?",
        "tags": ["결측치", "null", "개수", "단일숫자"],
        "template": """\
df = files["{FILE_A}"]
total_missing = int(df.isnull().sum().sum())
result = {"type": "number", "value": total_missing}""",
        "source": "builtin",
    },
]

# ── 정적 fallback (하위 호환) ─────────────────────────────────────────────────

EXAMPLES: dict[str, dict[str, str]] = {

    "filter": {
        "full": """\
## 참고 예시 — 데이터 필터링

사용자: "특정 값 이상인 행만 뽑아줘"
어시스턴트: 해당 컬럼 기준으로 조건에 맞는 행만 추출합니다.
```python
df = files["{FILE_A}"]
result = df[df["컬럼명"] >= 0]  # 0 → 사용자가 요청한 실제 기준값으로 교체
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
result = df[df["컬럼"] >= 0]           # 숫자 조건 (0 → 실제 기준값으로 교체)
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
```

사용자: "총 합계가 얼마야?" / "전체 건수가 몇 개야?" (단일 숫자 답변)
어시스턴트: 숫자 하나는 number 타입으로 반환합니다.
```python
df = files["{FILE_A}"]
total = int(df["숫자컬럼"].sum())
print(f"총합: {total:,}")
result = {"type": "number", "value": total}
```""",
        "compact": """\
## 집계 코드 패턴
```python
df = files["{FILE_A}"]
result = df.groupby("기준컬럼")["숫자컬럼"].sum().reset_index()        # 그룹 합계 → DataFrame
result = df.groupby("기준컬럼").agg({"숫자컬럼": ["sum","mean","count"]})
total = int(df["숫자컬럼"].sum())
result = {"type": "number", "value": total}                            # 단일 숫자
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

사용자: "파일들 키 기준으로 합쳐줘" (n개 join)
어시스턴트: 공통 키 컬럼을 기준으로 n개 파일을 순서대로 left join합니다.
  파일이 2개든 5개든 같은 패턴을 씁니다.
```python
dfs = list(files.values())

# 공통 키 후보: 첫 파일과 나머지 모두에 있는 문자형 컬럼
key_candidates = set(dfs[0].select_dtypes(exclude="number").columns)
for df in dfs[1:]:
    key_candidates &= set(df.select_dtypes(exclude="number").columns)
key_col = list(key_candidates)[0] if key_candidates else None
print(f"키 컬럼: {key_col}")

result = reduce(lambda left, right: pd.merge(left, right, on=key_col, how="left"), dfs)
print(f"병합 결과: {len(result)}행 × {len(result.columns)}열")
```

사용자: "같은 구조 파일 여러 개 세로로 붙여줘" (n개 concat)
어시스턴트: 동일 구조의 파일들을 수직으로 이어 붙입니다.
```python
result = pd.concat(list(files.values()), ignore_index=True)
print(f"총 {len(result)}행으로 합쳐짐")
```""",
        "compact": """\
## 병합 코드 패턴 (패턴 하나만 선택해서 사용할 것)
```python
# 패턴 A: n파일 key join (2개든 5개든 동일)
dfs = list(files.values())
key_candidates = set(dfs[0].select_dtypes(exclude="number").columns)
for df in dfs[1:]:
    key_candidates &= set(df.select_dtypes(exclude="number").columns)
key_col = list(key_candidates)[0]   # 추론된 키 컬럼
result = reduce(lambda l, r: pd.merge(l, r, on=key_col, how="left"), dfs)

# 패턴 B: n파일 세로 병합 (같은 구조)
result = pd.concat(list(files.values()), ignore_index=True)
```""",
    },

    "analyze": {
        "full": """\
## 참고 예시 — 탐색적 분석

사용자: "이 데이터 분석해줘"
어시스턴트: 결측치 현황과 수치형 컬럼을 코드로 확인한 뒤 실제 수치를 언급합니다.

```python
df = files["{FILE_A}"]

# 결측치 컬럼별 실제 개수
missing = df.isnull().sum()
missing = missing[missing > 0]
for col, cnt in missing.items():
    print(f"  {col}: {cnt}개")

# 수치형 컬럼 목록
num_cols = df.select_dtypes(include="number").columns.tolist()
print(f"수치형 컬럼: {num_cols}")

# 정리된 요약 테이블 (describe 대신)
result = pd.DataFrame({
    "항목": ["전체 행수", "전체 열수", "결측치 있는 컬럼 수", "수치형 컬럼 수"],
    "값": [len(df), len(df.columns), len(missing), len(num_cols)],
})
```

사용자: "수치 컬럼 분포 요약해줘"
어시스턴트: 평균·중앙값·이상값 의심 수를 실제 수치로 보여줍니다.
```python
df = files["{FILE_A}"]
rows = []
for col in df.select_dtypes(include="number").columns:
    s = df[col].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    outlier_cnt = int(((s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)).sum())
    rows.append({"컬럼": col, "평균": round(s.mean(), 1),
                 "중앙값": round(s.median(), 1), "이상값_의심": outlier_cnt})
result = pd.DataFrame(rows)
```

사용자: "막대 차트 그려줘" / "추세 그래프 보여줘"
어시스턴트: plt로 차트를 생성하고 fig를 plot 타입으로 반환합니다.
```python
df = files["{FILE_A}"]
cat_cols = df.select_dtypes(exclude="number").columns.tolist()
num_cols = df.select_dtypes(include="number").columns.tolist()
cat_col = cat_cols[0] if cat_cols else df.columns[0]
num_col = num_cols[0] if num_cols else df.columns[-1]
fig, ax = plt.subplots(figsize=(10, 5))
df.groupby(cat_col)[num_col].sum().plot(kind="bar", ax=ax, color="steelblue")
ax.set_title(f"{cat_col}별 {num_col} 합계")
ax.set_xlabel("")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
result = {"type": "plot", "value": fig}
```

사용자: "선 그래프로 추세 보여줘"
어시스턴트:
```python
df = files["{FILE_A}"]
num_cols = df.select_dtypes(include="number").columns.tolist()
num_col = num_cols[0] if num_cols else df.columns[-1]
fig, ax = plt.subplots(figsize=(10, 4))
df[num_col].plot(ax=ax, marker="o")
ax.set_title(f"{num_col} 추세")
plt.tight_layout()
result = {"type": "plot", "value": fig}
```

사용자: "파일들 분석해줘" / "데이터 파악해줘" (파일이 여러 개일 때)
어시스턴트: 파일별 구조를 먼저 정리하고 공통점·차이점을 짚어줍니다.

**{FILE_A}** vs **{FILE_B}** 구조:
- 공통 컬럼: [겹치는 컬럼명]
- {FILE_A}만: [고유 컬럼] / {FILE_B}만: [고유 컬럼]
- 결측치: {FILE_A}는 N개 컬럼, {FILE_B}는 M개 컬럼에 존재

```python
# 파일별 기본 현황 비교표
rows = []
for name, df in files.items():
    missing = df.isnull().sum()
    rows.append({
        "파일명": name,
        "행수": len(df),
        "열수": len(df.columns),
        "결측치_컬럼수": int((missing > 0).sum()),
        "수치형_컬럼수": len(df.select_dtypes(include="number").columns),
    })
result = pd.DataFrame(rows)

# 공통 컬럼 확인
names = list(files.keys())
if len(names) >= 2:
    common = set(files[names[0]].columns) & set(files[names[1]].columns)
    print(f"공통 컬럼 {len(common)}개: {', '.join(sorted(common))}")
```""",
        "compact": """\
## 분석 코드 패턴
```python
df = files["{FILE_A}"]
# 요약 테이블 (describe 대신)
missing = df.isnull().sum(); missing = missing[missing > 0]
num_cols = df.select_dtypes(include="number").columns.tolist()
result = pd.DataFrame({"항목": ["행수","열수","결측컬럼수","수치형컬럼수"],
                        "값": [len(df), len(df.columns), len(missing), len(num_cols)]})
# 차트
cat_cols = df.select_dtypes(exclude="number").columns.tolist()
num_cols = df.select_dtypes(include="number").columns.tolist()
cat_col = cat_cols[0] if cat_cols else df.columns[0]
num_col = num_cols[0] if num_cols else df.columns[-1]
fig, ax = plt.subplots(figsize=(10, 5))
df.groupby(cat_col)[num_col].sum().plot(kind="bar", ax=ax)
plt.tight_layout()
result = {"type": "plot", "value": fig}
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
result = df[df["컬럼"] >= 0]  # 0 → 사용자가 요청한 실제 기준값으로 교체
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

규칙: 파일이 여러 개면 모든 파일을 빠짐없이 답변합니다. 특정 파일명이 언급되지 않으면 전체 파일 기준으로 답하세요. 하나만 골라 답하지 마세요.

사용자: "컬럼이 뭐가 있어?"
어시스턴트:
**{FILE_A}** (N행): (실제 파일의 컬럼명을 그대로 나열) — 총 X개
**{FILE_B}** (M행): (실제 파일의 컬럼명을 그대로 나열) — 총 Y개

사용자: "몇 행이야?"
어시스턴트: {FILE_A} N행, {FILE_B} M행입니다.

사용자: "어떤 데이터야?"
어시스턴트: (샘플 행과 컬럼명을 참고해 파일 성격을 추정하고 파일별로 한 줄씩 요약)
**{FILE_A}**: N행 × M열. (실제 컬럼 구성 요약) — (데이터 성격 추정)
**{FILE_B}**: P행 × Q열. (실제 컬럼 구성 요약) — (데이터 성격 추정)

사용자: "파일 1개만 있을 때 — 컬럼이 뭐가 있어?"
어시스턴트: {FILE_A} 컬럼은 (실제 파일의 컬럼명을 그대로 나열) 총 X개입니다.

사용자: "결측치 몇 개야?" (단일 숫자로 충분한 경우)
어시스턴트:
```python
df = files["{FILE_A}"]
total_missing = int(df.isnull().sum().sum())
result = {"type": "number", "value": total_missing}
```""",
        "compact": """\
## 단순 질문 규칙
- 파일이 여러 개면 모든 파일 기준으로 답변 (첫 번째 파일만 고르지 말 것)
- 컬럼 목록·행 수는 파일 정보에서 코드 없이 바로 답변""",
    },
}
