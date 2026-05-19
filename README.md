# Excel AI Platform

<img width="1091" height="1071" alt="image" src="https://github.com/user-attachments/assets/1d9501a0-562c-4cc3-81ec-81d19a6af8fc" />

엑셀·CSV 파일을 업로드하고 AI와 대화하면서 데이터를 분석·변환·병합하는 Streamlit 기반 대화형 앱입니다.

**저장소:** [github.com/sayoon01/excel-ai-agent](https://github.com/sayoon01/excel-ai-agent)

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 멀티 모델 지원 | Ollama (로컬), Google Gemini, OpenAI GPT 중 선택 |
| 파일 관리 | xlsx / xls / csv 다중 업로드, 미리보기, 삭제 |
| 대화형 분석 | 자연어로 질문하면 AI가 pandas 코드를 생성하고 서버에서 실행 |
| 후속 작업 연결 | 직전 실행 결과(`last_result`)를 다음 요청에 자동으로 이어받아 처리 |
| 후속 질문 추천 | 답변 후 LLM이 이어서 할 만한 작업 3개를 버튼으로 제안 |
| 의도 배지 | 요청 의도(필터링/병합/집계 등)를 색상 배지로 표시 |
| 데이터 품질 요약 | 결측치·Unnamed·중복 컬럼·타입 불일치를 사이드바에서 즉시 확인 |
| 멀티 시트 경고 | xlsx에 시트가 여러 개일 경우 첫 시트만 읽힘을 경고 |
| 데이터 입력 범위 | 실제 값이 입력된 행·열 범위와 채워진 셀 밀도를 자동 탐지 |
| 결과 다운로드 | `save()`로 생성된 xlsx/csv를 사이드바에서 즉시 다운로드 |
| 대화보내기 | 전체 채팅을 `.md` 파일로 저장 |
| 프롬프트 디버그 | 사이드바에서 보강된 프롬프트·시스템 프롬프트 실시간 확인 |

---

## 빠른 시작

```bash
# 1. 저장소 클론
git clone https://github.com/sayoon01/excel-ai-agent.git
cd excel-ai-agent

# 2. 실행 (최초 1회 자동으로 가상환경 생성 및 패키지 설치)
./run.sh
```

브라우저에서 **http://localhost:8501** 접속

### 수동 실행

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Ollama 로컬 모델 사용 시

```bash
# Ollama 설치 후 원하는 모델 pull
ollama pull qwen2.5
ollama pull gemma3:27b
```

앱 실행 후 사이드바에서 설치된 모델이 자동으로 표시됩니다. Host 기본값은 `http://localhost:11434`입니다.

### Gemini / OpenAI

사이드바에서 API 키를 입력한 뒤 모델을 선택합니다. 키는 세션에만 유지되며 저장소에 커밋되지 않습니다.

---

## 프로젝트 구조

```
excel-ai-agent/
├── app.py                  # Streamlit 진입점 · 채팅 핸들러
├── run.sh                  # 실행 스크립트 (venv + streamlit)
├── requirements.txt
├── CODE_REVIEW.md          # 코드 리뷰 노트
├── .streamlit/
│   └── config.toml         # 다크 테마 설정
├── core/                   # 비즈니스 로직 (Streamlit 미사용)
│   ├── llm_client.py       # Ollama / Gemini / OpenAI 클라이언트
│   ├── prompt_builder.py   # 의도 감지 · 동적 시스템 프롬프트 ★
│   ├── code_executor.py    # 안전한 코드 실행 샌드박스
│   └── excel_processor.py  # 헤더 감지 · 사용 범위 탐지
├── services/               # I/O · 파일 시스템
│   ├── file_manager.py     # 업로드 · 목록 · 삭제 · 미리보기
│   └── export.py           # 대화보내기 (.md)
├── ui/                     # Streamlit 렌더링 전담
│   ├── sidebar.py          # 모델 설정 · 파일 · 결과 · 디버그
│   ├── chat_view.py        # 채팅 · 코드 실행 · 후속 질문 버튼
│   ├── quality_report.py   # 데이터 품질 요약 (사이드바)
│   └── components.py       # 의도 배지 등 공통 UI
├── tests/
│   └── test_used_range.py
├── uploads/                # 업로드 파일 (gitignore)
└── results/                # AI 생성 결과 파일 (gitignore)
```

### 레이어 역할

| 레이어 | 역할 | Streamlit 의존 |
|--------|------|----------------|
| `app.py` | 세션 상태 · LLM 호출 오케스트레이션 | ✅ |
| `ui/` | 화면 렌더링만 담당 | ✅ |
| `core/` | 프롬프트 · 코드 실행 · 엑셀 처리 | ❌ |
| `services/` | 파일 읽기/쓰기 ·보내기 | ❌ |

---

## 설계 방향

### 1. 대화 우선 설계

사용자가 짧게 입력해도 앱이 자동으로 맥락을 파악해서 LLM에 풍부한 프롬프트를 전달합니다. 코드 생성은 수단이고, 자연스러운 대화가 목적입니다.

<img width="766" height="512" alt="image" src="https://github.com/user-attachments/assets/caf235b7-c1f9-44d4-b6ff-136c8c1d66fe" />

### 2. 동적 프롬프트 파이프라인 (`core/prompt_builder.py`)

고정된 시스템 프롬프트 대신, 매 요청마다 상황에 맞는 프롬프트를 조합합니다.

**의도 감지 → 7종 분류**

| 의도 | 감지 키워드 예시 |
|------|----------------|
| filter | 필터, 뽑아, 추출, 이상, 이하 |
| merge | 병합, 합쳐, 통합, join |
| aggregate | 합계, 평균, 그룹, 집계 |
| transform | 변환, 추가, 정렬, 계산 |
| analyze | 분석, 통계, 요약, 패턴 |
| export | 저장, 다운로드,보내기 |
| query | 컬럼, 몇개, 뭐야, 보여줘 |

**페르소나 3개 분기**

```
analyze / query  →  analyst   (설명·인사이트 중심)
filter / aggregate / transform / export  →  engineer  (코드·정확성 중심)
merge  →  merger   (키 매칭·중복 처리 특화)
```

**사용자 프롬프트 자동 보강**

```
[입력]  "이거 합쳐줘"

[LLM이 실제로 받는 것]
이거 합쳐줘

---
[자동 컨텍스트]
요청에서 언급된 컬럼: 날짜
주의 — 'b.xlsx' 결측치: 담당자(12개)
직전 작업 결과(last_result): 500행 × 3열, 컬럼: 날짜, 매출, 지역
```

**시스템 프롬프트 조합**

<img width="755" height="505" alt="image" src="https://github.com/user-attachments/assets/818cd42b-7ffa-4062-8bf6-043721c28893" />

### 3. 후속 작업 연결 (`last_result`)

하나의 대화 세션 안에서 이전 실행 결과를 다음 요청의 입력으로 이어받습니다.

<img width="769" height="508" alt="image" src="https://github.com/user-attachments/assets/4d3fb762-6d46-4ac7-86ea-6b414f5d373c" />

세션 상태 구조:

```python
st.session_state
├── messages          # 대화 이력 (user: display + intent 포함)
├── exec_results      # 메시지별 코드 실행 결과
├── last_result       # 가장 최근 실행 결과 DataFrame
├── result_history    # 실행 이력 전체
├── last_intent       # 직전 감지된 의도
├── suggestions       # 메시지별 후속 질문 추천
└── pending_prompt    # 추천 버튼 클릭 시 다음 입력
```

"새 대화" 버튼을 누르면 `last_result`·`exec_results`·`suggestions`가 함께 초기화됩니다.

### 4. 코드 실행 샌드박스 (`core/code_executor.py`)

LLM이 생성한 pandas 코드를 서버에서 안전하게 실행합니다.

- **AST 검증**: `os`, `sys` 등 위험 모듈 및 모든 import 문 차단
- **pandas/numpy import 자동 제거**: LLM이 실수로 넣은 `import pandas`는 실행 전 strip (`pd`, `np`는 이미 주입됨)
- **30초 타임아웃**: 무한 루프 방지
- **격리된 네임스페이스**: `files`, `last_result`, `pd`, `np`, `save()`, `print()` 만 허용
- 실행 결과는 DataFrame으로 화면에 표시, `save("이름.xlsx")`로 `results/`에 저장

```python
# LLM 코드에서 사용 가능한 환경 (import 불필요)
df = files["파일명.xlsx"]
result = df[df["매출"] >= 100]
save("필터결과.xlsx")
```

### 5. 데이터 입력 범위 탐지 (`core/excel_processor.py`)

업로드된 파일에서 실제 값이 입력된 셀 범위를 자동으로 탐지합니다.

- **xlsx**: openpyxl 셀 이터레이션으로 min/max 행·열 계산
- **csv**: pandas `notna()` 마스크로 범위 추정
- 결과: `범위: 1행~50행 / 1열~5열 | 채워진 셀: 240/250 (96.0%)` 형태로 사이드바에 표시

### 6. 데이터 품질 요약 (`ui/quality_report.py`)

LLM 없이 업로드 직후 파일 메타데이터를 분석합니다.

- 사이드바 파일 미리보기 하단: 결측치 TOP 3, Unnamed·중복 컬럼·타입 불일치 배지
- `collect_files_info()` 결과를 `@st.cache_data`로 캐시해 반복 조회 비용 절감

### 7. 멀티 모델 추상화 (`core/llm_client.py`)

모든 프로바이더가 동일한 스트리밍 인터페이스를 사용합니다.

```python
client = get_client("Ollama", "qwen2.5", ollama_host="http://localhost:11434")
client = get_client("Gemini", "gemini-2.0-flash", api_key="...")
client = get_client("OpenAI", "gpt-4o", api_key="...")

for token in client.chat_stream(messages, system_prompt):
    ...
```

Ollama 소형 모델(7b/8b/3b/1b/mini 포함)은 compact 모드로 자동 전환되어 프롬프트 길이를 줄입니다.

---

## 지원 모델

**Ollama (로컬, 무료)**
- 설치된 모델 자동 감지 (qwen2.5, deepseek-coder, gemma3 등)
- 7b/8b/3b/1b/mini 포함 모델명은 compact 프롬프트 자동 적용

**Google Gemini**
- gemini-2.0-flash, gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash-thinking-exp

**OpenAI**
- gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-3.5-turbo

---

## 사용 예시

### 단순 질문
```
사용자: 컬럼이 뭐가 있어?
AI: a.xlsx의 컬럼은 날짜, 매출, 지역, 담당자, 상품명 총 5개입니다.
```

### 필터링
```
사용자: 매출 100 이상인 것만 뽑아줘
AI: 매출 컬럼 기준으로 100 이상인 행만 추출합니다.
    [코드 생성 → ▶ 코드 실행 버튼 → 결과 DataFrame 표시]
```

### 후속 필터링
```
사용자: 그중에서 서울만 보여줘
AI: 직전 결과에서 지역이 서울인 행만 추출합니다.
    [last_result 기반 코드 생성 → 실행]
```

### 후속 질문 추천
```
AI 답변 후 → [결측치 제거해줘] [Unnamed 열 삭제해줘] [지역별 합계해줘] 버튼 표시
버튼 클릭 → 해당 문장이 다음 입력으로 자동 전달
```

### 파일 병합
```
사용자: 이거 합쳐줘
AI: 두 파일의 공통 컬럼을 확인했습니다. '날짜'를 기준으로 병합할까요?
```

### 집계
```
사용자: 지역별 매출 합계 알려줘
AI: 지역 기준으로 그룹화해 매출 합계를 계산합니다.
    [코드 생성 → 실행 → 지역별 합계 표 + 다운로드 버튼]
```

---

## 기술 스택

| 구분 | 사용 |
|------|------|
| UI | Streamlit |
| 데이터 | pandas, numpy, openpyxl, xlrd |
| LLM | ollama, google-generativeai, openai |
| 실행 환경 | Python 3.12+ |

---

## 참고 레포지토리

- [SheetPilot](https://github.com/prof-lijar/sheetpilot) — 코드 실행 샌드박스, 파일 관리 구조 참고
- [cowork-llm-lab](https://github.com/YYeoeun/cowork-llm-lab) — 엑셀 헤더 감지, 다중 파일 병합 로직 참고
