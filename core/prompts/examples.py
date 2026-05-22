"""Intent별 few-shot 예시. {FILE_A}/{FILE_B}는 builder에서 실제 파일명으로 치환된다."""

EXAMPLES: dict[str, dict[str, str]] = {

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

사용자: "파일 3개 합쳐줘" (3개 이상 join)
어시스턴트: 순서대로 체이닝해서 병합합니다. result는 마지막 병합 후에만 한 번 할당합니다.
```python
df_a = files["{FILE_A}"]
df_b = files["{FILE_B}"]
df_c = list(files.values())[2]   # 세 번째 파일
step1 = pd.merge(df_a, df_b, on="키컬럼", how="left")
result = pd.merge(step1, df_c, on="키컬럼", how="left")
print(f"3파일 병합: {len(result)}행 × {len(result.columns)}열")
save("merged_all.xlsx")
```

사용자: "같은 구조 파일 여러 개 세로로 붙여줘"
어시스턴트: 동일 구조의 파일들을 수직으로 이어 붙입니다.
```python
result = pd.concat(list(files.values()), ignore_index=True)
print(f"총 {len(result)}행으로 합쳐짐")
save("combined.xlsx")
```""",
        "compact": """\
## 병합 코드 패턴 (패턴 하나만 선택해서 사용할 것)
```python
# 패턴 A: 2파일 left join
df_a, df_b = files["{FILE_A}"], files["{FILE_B}"]
result = pd.merge(df_a, df_b, on="키컬럼", how="left")
save("merged.xlsx")

# 패턴 B: 3파일 체이닝 join
df_a = files["{FILE_A}"]
df_b = files["{FILE_B}"]
df_c = list(files.values())[2]
step1 = pd.merge(df_a, df_b, on="키컬럼", how="left")
result = pd.merge(step1, df_c, on="키컬럼", how="left")
save("merged_all.xlsx")

# 패턴 C: 세로 병합 (같은 구조)
result = pd.concat(list(files.values()), ignore_index=True)
save("combined.xlsx")
```""",
    },

    "analyze": {
        "full": """\
## 참고 예시 — 탐색적 분석

사용자: "이 데이터 분석해줘"
어시스턴트: 결측치 현황과 수치형 컬럼을 실제 수치로 확인합니다.

결측치: 비목분류(22개), 비용명(18개), Unnamed:2(35개)
수치형 컬럼: 계획예산, 실행예산, 전년도집행
추천: Unnamed 열 제거 권장 / 결측 문자열 컬럼은 ffill 우선 검토

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
fig, ax = plt.subplots(figsize=(10, 5))
df.groupby("기준컬럼")["숫자컬럼"].sum().plot(kind="bar", ax=ax, color="steelblue")
ax.set_title("기준컬럼별 숫자컬럼 합계")
ax.set_xlabel("")
plt.xticks(rotation=45, ha="right")
plt.tight_layout()
result = {"type": "plot", "value": fig}
```

사용자: "선 그래프로 추세 보여줘"
어시스턴트:
```python
df = files["{FILE_A}"]
fig, ax = plt.subplots(figsize=(10, 4))
df.plot(x="날짜컬럼", y="숫자컬럼", ax=ax, marker="o")
ax.set_title("시계열 추세")
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
fig, ax = plt.subplots(figsize=(10, 5))
df.groupby("기준컬럼")["숫자컬럼"].sum().plot(kind="bar", ax=ax)
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

규칙: 파일이 여러 개면 모든 파일을 빠짐없이 답변합니다. 특정 파일명이 언급되지 않으면 전체 파일 기준으로 답하세요. 하나만 골라 답하지 마세요.

사용자: "컬럼이 뭐가 있어?"
어시스턴트:
**{FILE_A}** (N행): 날짜, 지역, 매출, 비용 — 총 4개
**{FILE_B}** (M행): 날짜, 부서, 예산, 집행 — 총 4개

사용자: "몇 행이야?"
어시스턴트: {FILE_A} N행, {FILE_B} M행입니다.

사용자: "어떤 데이터야?"
어시스턴트: (샘플 행을 참고해 내용을 추정하고 파일별로 한 줄씩 요약)
**{FILE_A}**: N행 × M열. 날짜·지역·매출 구성 — 판매 실적 데이터로 보입니다.
**{FILE_B}**: P행 × Q열. 부서·예산·집행 구성 — 예산 집행 현황 데이터로 보입니다.

사용자: "파일 1개만 있을 때 — 컬럼이 뭐가 있어?"
어시스턴트: {FILE_A} 컬럼은 날짜, 지역, 매출, 비용 총 4개입니다.

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
