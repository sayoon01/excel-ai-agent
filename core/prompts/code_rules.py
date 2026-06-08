"""LLM에게 전달하는 코드 작성 규칙."""

CODE_RULES = """\
## 코드 작성 규칙 (반드시 준수)

### 변수 환경
- `files` : {파일명: DataFrame} 딕셔너리 — 이미 로드 완료
- `pd`, `np` : 이미 주입됨 — 별도 import 없이 바로 사용
- `plt`, `matplotlib` : 이미 주입됨 — 별도 import 없이 바로 사용
- `reduce` : `functools.reduce` 이미 주입됨 — n개 파일 체이닝 병합 시 바로 사용
- `last_result` : 직전 실행 결과 DataFrame (없으면 None)
- `save("파일명.xlsx")` : 결과 파일 저장 함수
- `print()` : 중간 출력용

### ⛔ 절대 금지 — 아래 코드는 실행 즉시 오류 발생
- `import pandas`, `import numpy`, `from xxx import yyy` 등 import 문 전부 금지
  → pd, np는 이미 제공됨. 코드 첫 줄에 import 절대 쓰지 말 것
- `pd.read_excel()`, `pd.read_csv()`, `open()` 직접 호출 금지
  → files 딕셔너리에서 꺼내 쓸 것

### 파일 접근 패턴
```python
df = files["파일명.xlsx"]          # 특정 파일
for name, df in files.items():    # 전체 순회
    print(name, df.shape)
```

### ⛔ 절대 금지 — 다중 파일 단독 접근
파일이 2개 이상 로드되어 있고, 사용자 요청에 **특정 파일명이 명시되지 않은 경우**:
- `files["파일명.xlsx"]`로 하나만 접근하는 것은 **데이터 누락**입니다 → 금지
- 반드시 `for name, df in files.items():` 또는 `list(files.values())`로 **전체 파일 처리**하세요
```python
# ❌ 절대 금지 — 파일이 여러 개인데 하나만 처리
result = files["5예실대비표.xlsx"].iloc[:7].sum()

# ✅ 올바른 패턴 — 전체 파일 순회 후 파일별 결과를 DataFrame으로
rows = []
for name, df in files.items():
    row = {"파일명": name}
    # ... 파일별 처리 ...
    rows.append(row)
result = pd.DataFrame(rows)
```
특정 파일명이 사용자 요청에 **명시된 경우에만** `files["파일명.xlsx"]`로 단독 접근하세요.

### 분석 요약 패턴 (describe() 대신)
```python
rows = []
for name, df in files.items():
    rows.append({
        "파일명": name,
        "행수": len(df),
        "열수": len(df.columns),
        "결측치_총합": int(df.isnull().sum().sum()),
        "수치형_컬럼수": len(df.select_dtypes(include="number").columns),
    })
result = pd.DataFrame(rows)
```

### 결과 반환 형식
- DataFrame → `result = df` (기본, 항상 사용)
- 숫자 하나 → `result = {"type": "number", "value": 1234}`
- 텍스트 설명 → `result = {"type": "string", "value": "분석 결과: 총 1,234건"}`
- 차트 → `result = {"type": "plot", "value": fig}` (fig = plt.subplots()의 첫 번째 반환값)
- 최종 결과는 반드시 `result = ...`에 저장 (print()만 쓰면 표·다운로드가 나오지 않음)
- 파일로 저장하려면 `result = df` 이후에 `save("파일명.xlsx")` 호출 (순서 중요: result 먼저, save 나중)
  → save()를 생략하면 화면에만 표시되고, 채팅의 다운로드 버튼으로 받을 수 있음

### ⚠️ [CRITICAL] 파일 통합 — 반드시 구조 분석 후 판단

**Step 1 — 컬럼 구조 먼저 대조**
통합 전 모든 파일의 컬럼 목록을 비교하여 일치 비율을 계산하세요.
```python
dfs = list(files.values())
col_sets = [set(df.columns) for df in dfs]
common = col_sets[0].intersection(*col_sets[1:])
overlap_ratio = len(common) / max(len(col_sets[0]), 1)
print(f"공통 컬럼 {len(common)}개 / 비율 {overlap_ratio:.0%}")
```

**Step 2 — 구조가 같으면 수직 통합 (pd.concat)**
조건: 공통 컬럼 비율 ≥ 80% **AND** 같은 기간/지역/부서로 분할된 데이터일 때만 사용.
- 문자형 컬럼 전체를 key_cols로 자동 감지 → groupby 집계
- 수치형: mean / 문자형: first / 원본 컬럼 순서 유지

```python
dfs = [df.copy() for df in files.values()]
combined = pd.concat(dfs, ignore_index=True)
key_cols = [c for c in combined.columns if not pd.api.types.is_numeric_dtype(combined[c])]
num_cols = [c for c in combined.columns if pd.api.types.is_numeric_dtype(combined[c])]
agg_dict = {c: "mean" for c in num_cols}
result   = combined.groupby(key_cols, as_index=False).agg(agg_dict)
result   = result[[c for c in dfs[0].columns if c in result.columns]]
```

**Step 3 — 구조가 다르면 수평 결합 (pd.merge)**
조건: 컬럼 구조가 다르거나, 서로 다른 성격의 데이터일 때.
- 두 테이블을 연결할 수 있는 고유 식별자 컬럼(ID류·코드류·날짜류)을 반드시 찾아야 함
- 키가 명확하지 않으면 임의로 합치지 말고 `print()`로 후보를 출력하고 중단

```python
# 공통 컬럼 중 수치형을 제외하고, unique값 비율이 가장 높은 컬럼을 키로 선택
dfs = list(files.values())
common_cols = list(set(dfs[0].columns) & set(dfs[1].columns))
if not common_cols:
    print("공통 컬럼 없음 — 키 컬럼을 명시해 주세요")
    result = pd.DataFrame()
else:
    non_numeric = [c for c in common_cols if not pd.api.types.is_numeric_dtype(dfs[0][c])]
    candidates = non_numeric if non_numeric else common_cols
    key_col = max(candidates, key=lambda c: dfs[0][c].nunique() / max(len(dfs[0]), 1))
    print(f"선택된 키: {key_col}  (후보: {candidates})")
    result = pd.merge(dfs[0], dfs[1], on=key_col, how="left")
    print(f"병합 결과: {len(result)}행 × {len(result.columns)}열")
```

**⛔ 절대 금지 — concat 무단 사용**
- 컬럼 구조가 다른 파일에 `pd.concat`을 쓰는 것은 **데이터 오염**입니다.
- 키 컬럼을 모르는 상태에서 `pd.merge`를 임의로 실행하지 마세요.
- 구조 파악 없이 바로 통합 코드를 작성하지 마세요.

**단일 파일 집계**
→ `df.mean()` 또는 `df.groupby(...).agg(...)` 사용"""
