# Excel AI Platform — 코드 리뷰

작성일: 2026-05-19  
대상 커밋: 현재 main 브랜치 (총 ~1,960줄)

---

## 1. 전체 구조 평가

```
excel-platform/
├── app.py              # 진입점 + 채팅 핸들러
├── ui/                 # Streamlit 렌더링 전담
├── core/               # 비즈니스 로직 (UI 없음)
├── services/           # I/O, 파일 시스템
└── tests/
```

**좋은 점:** 3-레이어 분리가 명확하다. `core/`는 Streamlit을 import하지 않으며, `services/`는 외부 I/O만 담당한다. 새 기능을 추가할 때 어느 파일에 넣을지 판단하기 쉽다.

**아쉬운 점:** `app.py`에 아직 LLM 후속 질문 생성(`_generate_suggestions`), 클라이언트 팩토리(`_get_llm_client`), 프롬프트 상수(`_SUGGESTION_SYSTEM`)가 남아 있다. 이들은 `core/`로 이동할 후보다.

---

## 2. 파일별 리뷰

### `core/llm_client.py` ✅ 양호

```python
class LLMClient(ABC):
    @abstractmethod
    def chat_stream(self, messages, system_prompt) -> Generator[str, None, None]: ...
```

- ABC로 인터페이스가 명확히 정의되어 있어 새 프로바이더 추가가 쉽다.
- 각 클라이언트가 lazy import(`import ollama` 등을 `__init__` 내부에서)하는 방식이 올바르다. 미설치 패키지가 있어도 앱이 기동된다.

**버그:** `OllamaClient`가 `self._model`을 `__init__`에서 설정하지 않고 `with_model()`에 의존한다. `with_model()` 호출 없이 `chat_stream()`을 부르면 `AttributeError`가 발생한다.

```python
# 현재
class OllamaClient(LLMClient):
    def __init__(self, host):
        self._client = ollama.Client(host=host)
        # self._model 없음!

# 개선
class OllamaClient(LLMClient):
    def __init__(self, host, model: str = ""):
        self._client = ollama.Client(host=host)
        self._model = model
```

---

### `core/prompt_builder.py` ⚠️ 검토 필요

**좋은 점:**
- `detect_intent` → persona 선택 → `_EXAMPLES` 주입 → `_CODE_RULES` 조합 파이프라인이 명확하다.
- `compact` 모드로 소형 모델 대응이 잘 되어 있다.
- `# region` 폴딩으로 557줄 파일임에도 탐색이 편하다.

**개선 필요:**

1. **`_CODE_RULES` 안의 코드 예시가 실제 few-shot 예시와 중복된다.** `_EXAMPLES["analyze"]`에도 분석 패턴이 있고, `_CODE_RULES`에도 "분석 요약 패턴"이 있다. LLM이 두 곳에서 서로 다른 패턴을 받아 혼선이 생길 수 있다.

2. **`augment_user_prompt`의 컬럼 언급 감지가 단순 문자열 포함 방식이다.** 컬럼명이 `"수"`, `"명"` 같은 1-2자 한국어일 경우 false positive가 발생한다.

```python
# 현재 — 짧은 컬럼명에 취약
mentioned = [col for col in all_cols if col in raw_prompt]

# 개선 — 단어 경계를 고려
import re
mentioned = [col for col in all_cols if re.search(re.escape(col), raw_prompt) and len(col) >= 3]
```

3. **의도 감지 동점 처리가 dict 순서에 의존한다.** Python 3.7+에서는 삽입 순서가 보장되므로 현재는 괜찮지만, 명시적으로 우선순위를 정의하는 것이 더 안전하다.

---

### `core/code_executor.py` ✅ 양호

**좋은 점:**
- AST 기반 사전 검증으로 `exec` 전에 위험 코드를 차단한다.
- `_strip_preinjected_imports`로 `import pandas as pd` 같은 무해한 import를 조용히 제거해 UX를 개선했다.
- `_Timeout` 컨텍스트 매니저로 30초 무한루프를 방지한다.

**주의:**
- `signal.SIGALRM`은 **Linux/macOS 전용**이다. Windows에서 실행하면 타임아웃이 무음으로 비활성화된다(`except (ValueError, OSError): pass`). 현재 Linux 서버 전용이면 문제없으나, 이식성이 필요하면 `threading.Timer` 기반으로 교체해야 한다.

---

### `core/excel_processor.py` ⚠️ Dead Code

`describe_dataframe()`, `build_file_context()` 두 함수가 현재 어디서도 호출되지 않는다.

```python
# 현재 아무데서도 사용 안 됨
def describe_dataframe(df, fname): ...  # 삭제 대상
```

`services/file_manager.py`의 `build_file_context()` 함수도 동일하게 사용되지 않는다.

---

### `services/file_manager.py` ⚠️ 중복 I/O

`get_file_info()`가 한 파일에 대해 **3번** I/O를 수행한다.

```python
def get_file_info(name):
    df = read_file(name)          # I/O 1 — pandas 로드
    wb = openpyxl.load_workbook(path)  # I/O 2 — 시트 이름 읽기
    ur = get_used_range(path)      # I/O 3 — 또 openpyxl 로드 (내부)
```

`collect_files_info()`도 별도로 `read_file()`을 호출한다. 사이드바가 렌더링될 때마다 파일마다 최대 3회 I/O가 발생한다.

**개선 방향:** `get_used_range` 결과를 `get_file_info` 호출 시 같은 `openpyxl` 세션에서 계산하거나, `@st.cache_data`를 `get_file_info`에도 적용한다.

---

### `services/export.py` 🐛 버그

```python
def to_markdown(messages):
    for msg in messages:
        lines.append(f"## {role}\n\n{msg['content']}\n")
```

`msg['content']`는 **LLM에 전달된 보강된 프롬프트**다. 사용자가 입력한 원본은 `msg.get('display', msg['content'])`에 있다. 현재 내보내기 파일에는 `[자동 컨텍스트]` 섹션이 포함된 원시 프롬프트가 노출된다.

```python
# 개선
content = msg.get("display", msg["content"])
lines.append(f"## {role}\n\n{content}\n")
```

---

### `ui/quality_report.py` ⚠️ 미사용 함수

`render_quality_report()`가 메인 화면에서 제거된 후 현재 사용되지 않는다. 사이드바에서는 `render_compact_quality()`만 사용 중이다. 명시적으로 제거하거나 용도를 남겨둔다면 주석으로 표시한다.

---

### `ui/sidebar.py` ⚠️ 캐시 누락

디버그 expander 내부에서 `collect_files_info(list_files, read_file)`를 캐시 없이 직접 호출한다. debug input이 있을 때마다 파일 전체를 다시 읽는다. `load_files_info(tuple(list_files()))`로 교체하면 캐시를 활용할 수 있다.

---

### `ui/chat_view.py` ✅ 양호

- `split_response()`로 내러티브 텍스트와 코드를 분리해 expander에 넣는 구조가 깔끔하다.
- `render_last_result_banner()`가 별도 함수로 분리되어 있다.

**개선:** `render_chat_history()` 내부에 `render_follow_up_suggestions()` 호출이 포함되어 있어 함수 역할이 두 가지다. 후속 질문 렌더링을 호출부(`app.py`)로 올리면 각 함수의 책임이 단순해진다.

---

## 3. 캐시 전략 검토

```python
@st.cache_data(show_spinner=False)
def load_files_info(file_names: tuple) -> list[dict]:
    return collect_files_info(lambda: list(file_names), read_file)
```

**문제:** 캐시 키가 `tuple(file_names)` — 파일명만 본다. 같은 파일명으로 다른 내용을 업로드해도 캐시가 유지된다.

```python
# 개선 — 파일명 + 수정 시간을 키로 사용
from services.file_manager import UPLOAD_DIR

@st.cache_data(show_spinner=False)
def load_files_info(file_names: tuple) -> list[dict]:
    mtimes = tuple(
        (UPLOAD_DIR / name).stat().st_mtime
        for name in file_names
        if (UPLOAD_DIR / name).exists()
    )
    return _do_load(file_names, mtimes)

@st.cache_data(show_spinner=False)
def _do_load(file_names: tuple, mtimes: tuple) -> list[dict]:
    return collect_files_info(lambda: list(file_names), read_file)
```

---

## 4. 우선순위별 개선 항목

### 즉시 수정 권장 (버그)

| # | 위치 | 문제 | 영향 |
|---|------|------|------|
| 1 | `services/export.py:8` | `msg['content']` 대신 보강 프롬프트 노출 | 내보내기 파일 품질 |
| 2 | `core/llm_client.py` | `OllamaClient._model` 미초기화 | `AttributeError` 위험 |

### 단기 개선 (코드 품질)

| # | 위치 | 문제 |
|---|------|------|
| 3 | `core/excel_processor.py` | `describe_dataframe`, 미사용 함수 제거 |
| 4 | `services/file_manager.py` | `build_file_context` 미사용 함수 제거 |
| 5 | `ui/quality_report.py` | `render_quality_report` 미사용 함수 정리 |
| 6 | `ui/sidebar.py` | debug 섹션 캐시 누락 |
| 7 | `core/prompt_builder.py` | `augment_user_prompt` 짧은 컬럼명 false positive |

### 중기 개선 (아키텍처)

| # | 위치 | 문제 |
|---|------|------|
| 8 | `app.py` | `_generate_suggestions`, `_SUGGESTION_SYSTEM` → `core/prompt_builder.py` 이동 |
| 9 | `app.py` | `_get_llm_client` → `core/llm_client.py` 이동 |
| 10 | `services/file_manager.py` | `get_file_info` 중복 I/O 개선 |
| 11 | `ui/quality_report.py` | 캐시 키에 파일 수정 시간 포함 |

### 장기 고려

| # | 문제 |
|---|------|
| 12 | `signal.SIGALRM` — Linux 전용. 멀티플랫폼 필요 시 threading 기반 타임아웃으로 교체 |
| 13 | `collect_files_info`와 `get_file_info`의 계산 중복. 하나로 통합 고려 |

---

## 5. 잘 설계된 부분 요약

- **LLM 프로바이더 추상화** — `OllamaClient`, `GeminiClient`, `OpenAIClient` 모두 동일한 `chat_stream` 인터페이스 사용. 새 프로바이더 추가가 파일 하나 수정으로 끝난다.
- **`last_result` 체이닝** — 이전 실행 결과가 다음 프롬프트와 executor 네임스페이스에 자동 주입되는 설계가 깔끔하다.
- **AST 샌드박스** — exec 전 코드를 트리로 파싱해 import·위험 함수를 차단하는 방식이 정교하다.
- **pending_prompt 패턴** — 후속 질문 버튼 클릭 → session_state → rerun → chat_input으로 이어지는 Streamlit 관용 패턴을 올바르게 사용하고 있다.
- **`_strip_preinjected_imports`** — LLM이 import pandas를 생성해도 조용히 제거해 사용자에게 불필요한 오류를 노출하지 않는다.
- **intent → persona → few-shot 파이프라인** — 의도에 따라 다른 페르소나와 예시 코드를 조합하는 구조가 확장성이 높다.
