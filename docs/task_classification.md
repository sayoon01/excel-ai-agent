# Task 분류 시스템 설계

`core/routing/task_router.py`

---

## 핵심 원칙

> 자주 쓰는 명령은 rule로 빠르게, 애매할 때만 LLM, 그래도 모르면 code로 안전하게.

LLM 분류를 **매번 호출하지 않는 것**이 설계의 핵심이다.  
전체 요청의 ~80%는 rule에서 처리되고 LLM 호출 비용이 발생하지 않는다.

---

## 3단계 분류 흐름

```
사용자 입력
    │
    ▼
┌─────────────────────────────┐
│  1차: _rule_classify()      │  키워드 테이블 매칭 (비용 0)
│  confidence >= 0.80?        │
└────────────┬────────────────┘
             │ YES → 즉시 반환
             │ NO ↓
┌─────────────────────────────┐
│  2차: _llm_classify()       │  LLM JSON 분류 (애매한 경우만)
│  confidence >= 0.60?        │
└────────────┬────────────────┘
             │ YES → LLM 결과 반환
             │ NO ↓
┌─────────────────────────────┐
│  3차: code fallback         │  불확실 → 코드로 안전 처리
│  mode=code, needs_approval  │
└─────────────────────────────┘
```

코드:

```python
def classify_task(prompt: str, intent: str, client=None) -> dict:
    # 1차: rule
    task = _rule_classify(prompt, intent)
    if task["confidence"] >= 0.8:
        return task

    # 2차: LLM (애매한 경우만)
    task = _llm_classify(prompt, intent, client)

    if task["confidence"] < 0.6:
        return {                        # 3차: code fallback
            "mode": "code",
            "tool": None,
            "needs_summary":  task.get("needs_summary", False),
            "needs_export":   task.get("needs_export", False),
            "needs_approval": True,     # 불확실 → 사람이 확인
            "confidence":     task["confidence"],
        }

    return task
```

---

## 반환 형식

```json
{
  "mode": "tool",
  "tool": "aggregate_data",
  "needs_chart":    false,
  "needs_summary":  true,
  "needs_export":   false,
  "needs_approval": false,
  "use_last_result": false,
  "confidence": 0.92
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `mode` | `"tool"` \| `"code"` \| `"llm"` | 실행 모드 |
| `tool` | `str` \| `null` | tool 모드일 때 함수명 |
| `needs_chart` | bool | 차트 생성 추가 실행 여부 |
| `needs_summary` | bool | LLM 자연어 요약 추가 여부 |
| `needs_export` | bool | 결과 파일 저장 여부 |
| `needs_approval` | bool | Approval panel 강제 표시 여부 |
| `use_last_result` | bool | 이전 결과 DataFrame 체이닝 여부 |
| `confidence` | 0.0~1.0 | 분류 신뢰도 |

---

## 1차: Rule 기반 분류

### Tool 키워드 테이블 (`_TOOL_RULES`)

| 키워드 예시 | tool | confidence |
|-------------|------|-----------|
| 몇 행, 행수, 개수 | `get_row_count` | 0.97 |
| 결측치, 빈칸, missing | `analyze_missing` | 0.95 |
| 합계, 총합, sum | `aggregate_data` | 0.92 |
| 평균, mean, avg | `aggregate_data` | 0.92 |
| 최대, 최소, max, min | `aggregate_data` | 0.90 |
| 정렬, 내림차순, sort | `sort_rows` | 0.90 |
| 병합, 합치, join | `merge_files` | 0.90 |
| 필터 + 정렬 동시 | `filter_then_sort` | 0.90 |
| 필터, 추출, 조건 | `filter_rows` | 0.88 |
| 이상인, 상위, 포함된 | `filter_rows` | 0.86 |
| 저장, 다운로드, export | `export_data` | 0.88 |
| 산점도, scatter, 상관관계 | `create_chart` | 0.88 |
| 히스토그램, 분포도 | `create_chart` | 0.88 |
| 박스플롯, 사분위 | `create_chart` | 0.88 |
| 막대, bar | `create_chart` | 0.88 |
| 파이, pie, 원형 | `create_chart` | 0.88 |
| 차트, 그래프, 시각화 | `create_chart` | 0.80 |
| 선, line, 추이 | `create_chart` | 0.82 |
| 컬럼, 열, column | `get_profile` | 0.85 |

### LLM 키워드 테이블 (`_LLM_RULES`)

복잡도 힌트(`이면서`, `비교`, `상관`, `원인` 등)가 없을 때만 llm으로 분류.

| 키워드 | confidence |
|--------|-----------|
| 뭐야, 뭔가요 | 0.95 |
| 설명, 설명해줘 | 0.90 |
| 알려줘, 알려주세요 | 0.90 |
| 의미, 뜻, 차이 | 0.88 |
| 왜, 이유, 원인 | 0.85 |
| 어떻게 생각, 의견 | 0.85 |

### Code 키워드 테이블 (`_CODE_RULES`)

| 키워드 | confidence |
|--------|-----------|
| 단계별, 여러 조건, 복합 | 0.82 |
| 패턴, 추이 분석, 상관 | 0.80 |
| 이면서, 동시에, 그리고 | 0.78 |
| 분석, 분석해 | 0.75 |
| 비교, 대비 | 0.75 |

### 우선순위 처리 규칙

```
1. 차트 키워드 + 컬럼 키워드 동시 → create_chart 우선 (get_profile 충돌 방지)
2. 필터 키워드 + 정렬 키워드 동시 → filter_then_sort
3. tool 키워드 → tool 모드 (llm/code 키워드보다 우선)
4. llm 키워드 (복잡도 힌트 없을 때) → llm 모드
5. code 키워드 → code 모드
6. 아무것도 없으면 intent 기반 기본값
```

### Intent 기반 기본값 (키워드 없을 때)

| intent | mode | confidence |
|--------|------|-----------|
| export | tool | 0.75 |
| filter / aggregate / merge | tool | 0.70 |
| query | llm | 0.60 |
| analyze / transform | code | 0.65 |
| (기타) | code | 0.55 |

기본값 confidence는 모두 0.8 미만이므로 **2차 LLM 분류로 진입**한다.

---

## 2차: LLM 분류

1차에서 0.60 ≤ confidence < 0.80인 경우에만 호출된다.

**client가 없을 때** (Ollama 미연결 등):
```
rule 결과 confidence - 0.15
→ 대부분 < 0.60 → code fallback 진입
```

**client가 있을 때** — 아래 시스템 프롬프트로 JSON 1개 요청:

```
사용자 요청을 분석해 아래 JSON 형식으로만 반환하세요.
{"mode":"tool"|"code"|"llm", "tool":"함수명"|null,
 "needs_chart":bool, "needs_summary":bool, "needs_export":bool,
 "confidence":0.0~1.0}

mode 기준:
  tool: 행수/결측치/합계/평균/필터/정렬/병합/차트 등 정형 작업
  code: 복잡한 조건 분석, 다단계 변환, 비교/추이 분석
  llm : 설명/해석/질문 (데이터 처리 불필요)
```

LLM 파싱 실패 → rule 결과로 fallback, confidence=0.55 → **3차 code fallback 진입**.

---

## 3차: Code Fallback

LLM도 0.60 미만이면 "무엇을 해야 할지 모른다"는 뜻이다.  
이때 code 모드로 보내고 `needs_approval: True`를 붙인다.

```
사용자 → 코드 생성 → Approval panel (사람 확인) → 실행
```

`needs_approval: True`는 신뢰도가 낮아서 자동 실행하면 위험할 수 있다는 명시적 표시다.  
Approval panel은 이 필드를 보고 강제 표시한다.

---

## 보조 감지: `_detect_options()`

mode 분류와 독립적으로 항상 실행되어 반환값에 추가된다.

| 옵션 | 감지 키워드 |
|------|------------|
| `needs_chart` | 차트, 그래프, 시각화, scatter, histogram … |
| `needs_summary` | 요약, 정리, 해석, 인사이트 … |
| `needs_export` | 저장, 다운로드, 내보내기, export … |
| `use_last_result` | 방금, 이전 결과, 그 결과, 필터한 결과 … |

---

## 예시

| 입력 | 1차 결과 | 최종 mode | tool |
|------|---------|----------|------|
| `"행수 알려줘"` | conf=0.97 | **tool** | `get_row_count` |
| `"합계 구해줘"` | conf=0.92 | **tool** | `aggregate_data` |
| `"필터 후 정렬"` | conf=0.90 | **tool** | `filter_then_sort` |
| `"산점도 그려줘"` | conf=0.88 | **tool** | `create_chart` |
| `"이게 뭐야"` | conf=0.95 | **llm** | — |
| `"분석해줘"` | conf=0.75 → LLM | **code** or **tool** | LLM 판단 |
| `"원인 찾아줘"` | conf=0.85 → 복잡도 힌트 → code | **code** | — |
| `"이면서 비교해줘"` | conf=0.78 → LLM → 불확실 | **code** + `needs_approval` | — |

---

## needs_approval 필드 추가 이유

| 경우 | needs_approval |
|------|---------------|
| 1차 rule 명확 (conf ≥ 0.80) | `False` |
| 2차 LLM 분류 성공 (conf ≥ 0.60) | `False` |
| 3차 code fallback (conf < 0.60) | **`True`** |

Approval panel은 원래 `state.has_code && state.mode != "llm"`이면 자동 표시된다.  
`needs_approval: True`를 별도로 두면:
- task_config만 봐도 "이 요청은 사람이 확인해야 함"을 알 수 있다
- 향후 조건 변경 시 approval panel 로직 한 곳에서만 수정하면 된다
- 로그·히스토리에서 "얼마나 자주 fallback이 발생했는가"를 추적할 수 있다
