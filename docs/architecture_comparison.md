# 실행 구조 비교: 현재 방식 vs Tool Calling

작성일: 2026-05-22

---

## 1. 현재 구조 — 코드 생성 + exec() 실행

### 흐름

```
사용자 입력
    │
    ▼
detect_intent()          # "필터해줘" → intent: filter
    │
    ▼
build_system_prompt()    # 페르소나 + 파일 정보 + CODE_RULES 조합
    │
    ▼
LLM 호출 (chat_stream)
    │
    │  LLM 응답 (텍스트):
    │  "네, 필터하겠습니다.
    │   ```python
    │   result = files["sales.xlsx"]
    │   result = result[result["매출"] > 1000]
    │   ```"
    │
    ▼
```python 블록 추출 (정규식)
    │
    ▼
code_executor.execute()
    ├─ AST 검증 (위험 코드 차단)
    ├─ exec(code, namespace)
    │    └─ namespace: {files, pd, np, plt, last_result}
    └─ result 변수 회수
    │
    ▼
DataFrame / 차트 / 숫자 표시
```

### 핵심 파일

| 파일 | 역할 |
|------|------|
| `core/pipeline_executor.py` | intent 분류 → persona → prompt 보강 |
| `core/prompts/builder.py` | 시스템 프롬프트 조합 |
| `core/prompts/code_rules.py` | LLM에게 코드 형식 지시 |
| `core/prompts/examples.py` | 의도별 올바른 코드 예시 |
| `core/code_executor.py` | AST 검증 + exec() 실행 + 재시도 |
| `ui/chat_view.py` | 응답에서 ```python 블록 감지 |
| `ui/approval_panel.py` | 실행 전 사용자 승인 UI |
| `ui/thinking_panel.py` | 처리 단계 / 토큰 / 시간 표시 |

---

## 2. Tool Calling 구조

### 흐름

```
사용자 입력
    │
    ▼
LLM 호출
    │
    │  LLM 응답 (JSON):
    │  {
    │    "name": "filter_rows",
    │    "arguments": {
    │      "column": "매출",
    │      "operator": ">",
    │      "value": 1000
    │    }
    │  }
    │
    ▼
함수 이름으로 미리 정의된 함수 검색
    │
    ▼
filter_rows(column="매출", operator=">", value=1000) 직접 호출
    │
    ▼
결과를 다시 LLM에 전달 → 최종 자연어 응답 생성
    │
    ▼
사용자에게 표시
```

### 미리 정의해야 할 함수 예시

```python
# 이런 함수들을 모두 사전에 만들어야 함
def filter_rows(df, column, operator, value): ...
def group_by(df, columns, agg_func): ...
def merge_files(file_a, file_b, on, how): ...
def create_chart(df, chart_type, x, y): ...
def export_file(df, filename, format): ...
```

---

## 3. 비교

### 구조 차이

```
현재 구조 (코드 생성)               Tool Calling
─────────────────────────────────   ─────────────────────────────────
LLM이 Python 코드를 텍스트로 생성    LLM이 JSON으로 함수 호출 명세 출력
      ↓                                    ↓
  exec()로 실행                       미리 정의된 함수 직접 호출
      ↓                                    ↓
result 변수 회수                      반환값을 다시 LLM에 전달
                                           ↓
                                      LLM이 최종 응답 생성
```

### 특성 비교

| 항목 | 현재 구조 | Tool Calling |
|------|-----------|--------------|
| **유연성** | ✅ 높음 — LLM이 임의 pandas 코드 작성 가능 | ❌ 낮음 — 미리 정의된 함수만 호출 가능 |
| **안정성** | ⚠️ 낮음 — 코드 오류 발생 가능 | ✅ 높음 — 함수는 사전 검증됨 |
| **예측 가능성** | ❌ 낮음 — 매번 다른 코드 생성 | ✅ 높음 — 항상 동일한 함수 호출 |
| **확장성** | ✅ 즉시 — 새 기능 = 프롬프트 수정 | ❌ 느림 — 새 기능 = 함수 개발 필요 |
| **오류 시** | 자동 재시도 (execute_with_retry) | 함수 자체 오류 처리 |
| **사용자 개입** | 실행 전 코드 확인/수정 가능 | 함수 호출 전 개입 어려움 |
| **복잡한 로직** | ✅ 가능 — 다단계 pandas 체이닝 | ❌ 어려움 — 함수 조합으로만 표현 |
| **보안** | AST 검증 + 샌드박스 | 함수 단위 권한 제어 |
| **구현 비용** | 낮음 (현재 구현됨) | 높음 (함수 정의 + 스키마 관리) |

---

## 4. 현재 구조가 이 프로젝트에 적합한 이유

### 엑셀 분석 특성

엑셀 데이터 분석은 요청이 매우 다양하고 예측 불가능합니다.

```
"집행률이 80% 미만이고 전년 대비 감소한 항목만 뽑아서
 부서별로 합산한 다음 상위 5개만 보여줘"
```

이런 복잡한 조건은 Tool Calling으로 표현하려면 수십 개의 함수 조합이 필요하지만, 현재 구조에서는 LLM이 pandas 코드 몇 줄로 처리합니다.

### 현재 구조의 안전장치

Tool Calling 없이도 안전성을 확보한 이유:

```
위험 코드 차단    → AST 검증 (BLOCKED_MODULES, BLOCKED_BUILTINS)
무한루프 방지     → signal.SIGALRM 30초 타임아웃
파일 접근 제한    → namespace에 허용된 files만 주입
오류 자동 수정    → execute_with_retry() LLM 재시도
실행 전 검토      → approval_panel [실행] [수정] [건너뛰기]
```

---

## 5. Tool Calling이 유리한 경우

현재 구조를 유지하되, 아래 상황이 생기면 Tool Calling 도입을 검토합니다.

| 상황 | 이유 |
|------|------|
| 동일 작업을 수백 번 반복 실행 | 코드 생성 비용이 누적됨 |
| 외부 API 연동 필요 | 함수 단위 권한 제어가 명확함 |
| 비개발자가 직접 도구 추가 | 함수 정의가 더 직관적 |
| 응답 형식이 완전히 고정된 경우 | Tool Calling이 더 일관됨 |
