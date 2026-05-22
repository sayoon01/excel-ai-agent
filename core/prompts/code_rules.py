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
- 파일명을 지정하려면 `result = df` 이후에 `save("파일명.xlsx")` 호출 (순서 중요: result 먼저, save 나중)
  → save()를 생략하면 타임스탬프 파일명(result_YYYYMMDD_HHMMSS.xlsx)으로 자동 저장됨

### 파일 통합 패턴 선택 기준

**같은 구조의 여러 파일을 하나로 합칠 때** (동일 양식 통합, 항목별 평균)
→ `pd.concat` 으로 세로 결합 후 항목 기준 집계
- key 컬럼: 비수치형 컬럼 전체를 자동 감지 (컬럼명을 코드에 직접 쓰지 않음)
- 수치형 컬럼 → `groupby(key_cols).mean()`
- 문자형 컬럼 → `.agg("first")`, 결과 컬럼 순서는 원본과 동일하게 유지

```python
dfs = [df.copy() for df in files.values()]
combined = pd.concat(dfs, ignore_index=True)
key_cols = [c for c in combined.columns if not pd.api.types.is_numeric_dtype(combined[c])]
num_cols = [c for c in combined.columns if pd.api.types.is_numeric_dtype(combined[c])]
agg_dict = {c: "mean" for c in num_cols}
result   = combined.groupby(key_cols, as_index=False).agg(agg_dict)
result   = result[[c for c in dfs[0].columns if c in result.columns]]
```

**스키마가 다른 파일을 키 기준으로 연결할 때** (join, 좌우 결합)
→ `pd.merge` 사용

**단일 파일에서 컬럼 평균·합계를 보여줄 때**
→ `df.mean()` 또는 `df.groupby(...).agg(...)` 사용"""
