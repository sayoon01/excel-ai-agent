# Excel AI Platform

<img width="1408" height="2338" alt="image" src="https://github.com/user-attachments/assets/355c5062-8ed8-4b97-a948-36584a4282ae" />


엑셀·CSV 파일을 업로드하고 AI와 대화하면서 데이터를 분석·변환·병합하는 Streamlit 기반 대화형 앱입니다.



---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 멀티 모델 지원 | Ollama (로컬), Google Gemini, OpenAI GPT 중 선택 |
| 파일 관리 | xlsx / xls / csv 다중 업로드, 중복 처리, 멀티 시트 선택, 전체 보기 |
| 대화형 분석 | 자연어로 질문하면 AI가 pandas 코드를 생성하고 서버에서 실행 |
| 파일 선택 pills | 채팅 화면에서 분석할 파일을 pill 버튼으로 다중 선택 |
| 페르소나 관리 | 분석가·엔지니어·병합 전문가 등 AI 역할을 화면에서 생성·편집·복제 |
| 채팅 페르소나 선택 | 채팅 중 페르소나를 pill로 즉시 전환 (자동 / 수동) |
| 데이터 품질 프로파일링 | 결측률·중복·집계행·이상값·타입 혼재를 규칙 기반으로 자동 진단 |
| AI 품질 코멘트 | 진단 결과를 LLM이 한국어로 요약 (1회 생성 후 영구 캐시) |
| 구조화된 결과 타입 | DataFrame · 숫자 · 텍스트 · 차트를 타입별로 렌더링 |
| 코드 오류 자동 수정 | 실행 실패 시 에러를 LLM에게 돌려보내 수정 코드 자동 재실행 |
| 후속 작업 연결 | 직전 실행 결과(`last_result`)를 다음 요청에 자동으로 이어받아 처리 |
| 후속 질문 추천 | 답변 후 LLM이 이어서 할 만한 작업 3개를 버튼으로 제안 |
| 의도 배지 | 요청 의도(필터링/병합/집계/차트 등)를 색상 배지로 표시 |
| 결과 자동 저장 | `result` DataFrame이 있으면 `results/`에 xlsx로 자동 저장·다운로드 |
| 대화 내보내기 | 전체 채팅을 `.md` 파일로 저장 |

---

## 빠른 시작

```bash
# 저장소 클론
git clone https://github.com/sayoon01/excel-ai-agent.git
cd excel-ai-agent

# 실행 (최초 1회 가상환경 생성 및 패키지 설치)
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

### Ollama 로컬 모델

```bash
ollama pull qwen2.5
ollama pull gemma3:27b
```

앱 실행 후 설정 탭에서 설치된 모델이 자동으로 표시됩니다.

---

## 프로젝트 구조

```
excel-platform/
├── app.py                      # st.navigation() 진입점
├── data/
│   └── personas.json           # 페르소나 데이터 (프리셋 + 커스텀)
├── pages/
│   ├── 0_채팅.py               # AI 채팅 + 파일·페르소나 선택
│   ├── 1_파일관리.py            # 업로드, 미리보기, 품질 리포트
│   ├── 2_설정.py               # LLM 모델 설정
│   └── 3_페르소나.py            # 페르소나 관리 UI
├── core/                       # 비즈니스 로직 (Streamlit 미사용)
│   ├── llm_client.py           # Ollama / Gemini / OpenAI 클라이언트
│   ├── code_executor.py        # 안전한 코드 실행 샌드박스
│   ├── excel_processor.py      # 헤더 감지 · 사용 범위 탐지
│   ├── intent.py               # 의도 분류 (7종)
│   ├── persona_manager.py      # 페르소나 CRUD + intent 매핑
│   ├── quality_rules.py        # 데이터 품질 프로파일링 규칙
│   ├── chat_history.py         # 대화 이력 저장
│   └── prompts/
│       ├── builder.py          # 동적 system prompt 조합
│       ├── code_rules.py       # 코드 생성 규칙
│       └── examples.py         # intent별 few-shot 예시
├── services/
│   ├── file_manager.py         # 업로드 · 목록 · 삭제 · 미리보기
│   ├── comment_cache.py        # LLM 품질 코멘트 영구 캐시
│   └── export.py               # 대화 내보내기 (.md)
├── ui/
│   ├── helpers.py              # 세션 상태 초기화 · LLM 클라이언트 팩토리
│   ├── sidebar.py              # 모델 설정 · 파일 업로드
│   ├── chat_view.py            # 채팅 렌더링 · 코드 실행 · 후속 질문
│   ├── quality_report.py       # 품질 리포트 UI
│   ├── persona_panel.py        # 페르소나 관리 UI
│   └── components.py           # 의도 배지 등 공통 UI
├── docs/
│   └── persona_system_design.md
├── tests/
├── uploads/                    # 업로드 파일 (gitignore)
└── results/                    # 결과 파일 · LLM 코멘트 캐시 (gitignore)
```

### 레이어 아키텍처

```mermaid
graph TD
    subgraph Pages
        P0["💬 0_채팅.py"]
        P1["📂 1_파일관리.py"]
        P2["⚙️ 2_설정.py"]
        P3["🎭 3_페르소나.py"]
    end

    subgraph UI["ui/"]
        HLP["helpers.py\n세션·클라이언트"]
        CHV["chat_view.py\n채팅 렌더링"]
        QR["quality_report.py\n품질 리포트"]
        PP["persona_panel.py\n페르소나 관리"]
        SB["sidebar.py"]
    end

    subgraph Core["core/"]
        LC["llm_client.py\nOllama/Gemini/OpenAI"]
        CE["code_executor.py\n샌드박스 실행"]
        PM["persona_manager.py\nCRUD + intent 매핑"]
        QU["quality_rules.py\n품질 프로파일링"]
        BD["prompts/builder.py\nsystem prompt 조합"]
        IT["intent.py\n의도 분류"]
    end

    subgraph Services["services/"]
        FM["file_manager.py\n파일 I/O"]
        CC["comment_cache.py\nLLM 코멘트 캐시"]
        EX["export.py\n대화 내보내기"]
    end

    subgraph Data["data/"]
        PJ["personas.json"]
    end

    P0 --> CHV
    P0 --> HLP
    P1 --> QR
    P3 --> PP
    CHV --> CE
    CHV --> HLP
    QR --> CC
    PP --> PM
    BD --> PM
    BD --> IT
    PM --> PJ
    FM --> QU
    QR --> FM
```

---

## 설계 방향

### 1. 전체 요청 처리 흐름

```mermaid
flowchart TD
    Input["💬 사용자 입력"]
    Intent["intent 분류\ndetect_intent() → 7종"]
    Persona{"페르소나 결정"}
    AutoP["자동: resolve_persona_key(intent)"]
    ManualP["수동: pills에서 선택"]
    Build["system prompt 조합\nbuilder.py\n페르소나 + 파일 정보 + 맥락 + CODE_RULES"]
    Augment["user prompt 보강\naugment_user_prompt()\n컬럼명 · 결측치 자동 주입"]
    LLM["LLM 호출 streaming\nOllama / Gemini / OpenAI"]
    Response["응답 표시\n텍스트 + 코드 expander"]
    ExecBtn["▶ 코드 실행 버튼"]
    Exec["code_executor.py\nAST 검증 → exec → 결과"]
    Result["결과 렌더링\nDataFrame / 숫자 / 차트"]
    AutoSave["results/ 자동 저장\n+ 다운로드 버튼"]
    Retry["실패 시 LLM 자동 수정\n최대 2회 재시도"]
    Followup["후속 질문 3개 생성\n_generate_suggestions()"]

    Input --> Intent
    Intent --> Persona
    Persona -->|자동| AutoP
    Persona -->|수동| ManualP
    AutoP --> Build
    ManualP --> Build
    Build --> Augment
    Augment --> LLM
    LLM --> Response
    Response --> ExecBtn
    ExecBtn --> Exec
    Exec -->|성공| Result
    Exec -->|실패| Retry
    Retry --> Exec
    Result --> AutoSave
    Response --> Followup
```

### 2. 동적 프롬프트 파이프라인

고정된 시스템 프롬프트 대신, 매 요청마다 상황에 맞는 프롬프트를 조합합니다.

**의도 감지 → 7종 분류**

| 의도 | 감지 키워드 예시 | 연결 페르소나 |
|------|----------------|-------------|
| filter | 필터, 뽑아, 추출, 이상, 이하 | 엔지니어 |
| merge | 병합, 합쳐, 통합, join | 병합 전문가 |
| aggregate | 합계, 평균, 그룹, 집계 | 엔지니어 |
| transform | 변환, 추가, 정렬, 계산 | 엔지니어 |
| analyze | 분석, 통계, 차트, 시각화 | 분석가 |
| export | 저장, 다운로드, 내보내기 | 엔지니어 |
| query | 컬럼, 몇개, 뭐야, 보여줘 | 분석가 |

**페르소나 3종 + 커스텀**

```mermaid
graph LR
    analyze --> analyst["🧑‍💼 분석가\n설명·인사이트 중심"]
    query --> analyst
    filter --> engineer["👨‍💻 엔지니어\n코드·정확성 중심"]
    aggregate --> engineer
    transform --> engineer
    export --> engineer
    merge --> merger["🔗 병합 전문가\n키 매칭·중복 처리 특화"]
    other["매핑 없음"] -->|fallback| analyst
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

### 3. 페르소나 관리 시스템

페르소나 데이터를 `data/personas.json`에 저장해 코드 수정 없이 화면에서 관리합니다.

```mermaid
flowchart LR
    J[("data/personas.json")]
    PM["persona_manager.py\nCRUD"]
    BD["builder.py\nprompt 조합"]
    PP["persona_panel.py\n관리 UI"]
    CH["0_채팅.py\npills 선택기"]

    J <-->|읽기/쓰기| PM
    PM --> BD
    PM --> PP
    BD --> CH
```

- **프리셋**: 편집·복제만 가능, 삭제 불가
- **커스텀**: 생성·편집·복제·삭제 전부 가능
- System Prompt를 비워두면 About + Response style로 자동 생성

### 4. 코드 실행 샌드박스

```mermaid
flowchart TD
    Code["LLM 생성 코드"]
    Strip["import 자동 제거\n_strip_preinjected_imports()"]
    AST["AST 검증\n위험 모듈·함수 차단"]
    Fail1["❌ 검증 실패\n오류 반환"]
    Exec["exec() 실행\n격리된 네임스페이스\n30초 타임아웃"]
    Fail2["❌ 실행 실패"]
    Retry["LLM 자동 수정\n최대 2회"]
    Result["result 변수 분류\nDataFrame / 숫자 / 문자 / 차트"]
    Save["results/ 자동 저장\n+ 다운로드 버튼"]

    Code --> Strip --> AST
    AST -->|위반| Fail1
    AST -->|통과| Exec
    Exec -->|예외| Fail2
    Fail2 --> Retry --> Exec
    Exec -->|성공| Result --> Save
```

**실행 환경 (import 불필요)**

```python
df = files["파일명.xlsx"]       # 업로드된 파일 dict

result = df[df["매출"] >= 100]  # DataFrame 반환 → st.dataframe()
result = {"type": "number", "value": df["매출"].sum()}   # st.metric()
result = {"type": "plot",   "value": fig}                # 인라인 차트
save("결과.xlsx")               # results/ 저장 + 다운로드 버튼
```

### 5. 데이터 품질 프로파일링

```mermaid
flowchart LR
    DF["DataFrame"]
    PQ["profile_quality()\ncore/quality_rules.py"]
    M["결측률 per 컬럼"]
    D["중복 행 수"]
    S["집계행 감지\n소계·합계·총계"]
    O["IQR×3 이상값"]
    MT["타입 혼재 컬럼"]
    C["상수 컬럼"]
    BFP["bullets_from_profile()\n임계값 필터링 + 한국어 변환"]
    UI["주요 진단 결과\n· 비용명 결측률 40%\n· 집계행 2개 포함 가능성"]
    AI["✨ AI 코멘트 생성\nLLM 3~5문장 요약"]
    Cache["comment_cache.py\nJSON 영구 캐시\n파일명+profile 해시 키"]

    DF --> PQ
    PQ --> M & D & S & O & MT & C
    M & D & S & O & MT & C --> BFP --> UI
    UI --> AI --> Cache
```

---

## 기술 스택

| 구분 | 사용 |
|------|------|
| UI | Streamlit 1.57 (`st.navigation`, `st.pills`, `st.dialog`) |
| 데이터 | pandas, numpy, openpyxl, xlrd, matplotlib |
| LLM | ollama, google-generativeai, openai |
| 실행 환경 | Python 3.12+ |

---

## 참고 레포지토리

- [SheetPilot](https://github.com/prof-lijar/sheetpilot) — 코드 실행 샌드박스, 파일 관리 구조
- [cowork-llm-lab](https://github.com/YYeoeun/cowork-llm-lab) — 엑셀 헤더 감지, 다중 파일 병합 로직
- [PandasAI](https://github.com/sinaptik-ai/pandas-ai) — 에러 자동 수정, 수치 통계 컨텍스트 주입
- [excelchat-streamlit](https://github.com/frank-flin/excelchat-streamlit) — 대화 히스토리 시스템 프롬프트 주입 구조
