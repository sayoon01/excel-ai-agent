# 페르소나 기반 Prompt 시스템 가이드

## 구조 한눈에 보기

```mermaid
graph TD
    JSON["📄 data/personas.json\n모든 페르소나 데이터\n프리셋 + 커스텀"]
    PM["⚙️ core/persona_manager.py\nCRUD + intent 매핑"]
    B["🔧 core/prompts/builder.py\nsystem prompt 조합"]
    UI["🖥️ ui/persona_panel.py\nStreamlit 관리 UI"]
    P3["📑 pages/3_페르소나.py\n관리 페이지 진입점"]
    P0["💬 pages/0_채팅.py\n페르소나 pills 선택기"]

    JSON --> PM
    PM --> B
    PM --> UI
    UI --> P3
    B --> P0
```

핵심 원칙: **데이터(JSON)와 로직(Python)을 분리**  
페르소나를 추가·수정할 때 코드를 건드리지 않고 화면에서 직접 관리합니다.

---

## personas.json 스키마

**위치:** `data/personas.json`

```json
{
  "personas": {
    "analyst": {
      "name": "데이터 분석가",
      "description": "숫자를 해석하고 패턴을 발견해 설명하는 전문가",
      "type": "preset",
      "about": "한국어로 대화하는 데이터 분석 전문가",
      "response_style": "친근하고 간결하게, 핵심 2가지 이내",
      "system_prompt": "## 역할\n당신은 ...",
      "intents": ["analyze", "query"],
      "created_at": "2026-05-22T00:00:00",
      "updated_at": "2026-05-22T00:00:00"
    }
  },
  "default_persona": "analyst",
  "intent_fallback": "analyst"
}
```

### 필드 설명

| 필드 | 타입 | 설명 |
|---|---|---|
| `name` | string | 화면에 표시할 이름 (한국어) |
| `description` | string | 한 줄 요약 |
| `type` | `"preset"` \| `"custom"` | 프리셋은 삭제 불가, 커스텀은 자유 |
| `about` | string | 이 페르소나가 어떤 역할인지 설명 |
| `response_style` | string | 말투·응답 스타일 요약 |
| `system_prompt` | string | LLM에 실제 전달되는 전체 텍스트 |
| `intents` | list[str] | 이 페르소나가 자동 선택되는 intent 목록 |

---

## Intent → Persona 자동 매핑

```mermaid
graph LR
    analyze["analyze\n분석해줘, 차트"] --> analyst["🧑‍💼 analyst\n데이터 분석가"]
    query["query\n뭐야, 보여줘"] --> analyst

    filter["filter\n필터, 추출"] --> engineer["👨‍💻 engineer\n데이터 엔지니어"]
    aggregate["aggregate\n합계, 그룹"] --> engineer
    transform["transform\n변환, 추가"] --> engineer
    export["export\n저장, 내보내기"] --> engineer

    merge["merge\n병합, 통합"] --> merger["🔗 merger\n데이터 병합 전문가"]

    other["매핑 없는 intent"] -->|fallback| analyst
```

---

## persona_manager.py — CRUD 흐름

```mermaid
flowchart LR
    J[("📄 personas.json")]

    J -->|읽기| R["list_personas()\nget_persona()"]
    C["create_persona()"] -->|쓰기| J
    U["update_persona()"] -->|쓰기| J
    DUP["duplicate_persona()\nsource → custom 복제"] -->|쓰기| J

    DEL{"delete_persona()"}
    DEL -->|type == preset| ERR["❌ PermissionError\n삭제 불가"]
    DEL -->|type == custom| J2["✅ JSON에서 제거"]
```

### resolve_persona_key

```python
# intent에 매핑된 페르소나 키 반환
# 매핑 없으면 intent_fallback("analyst") 반환
key = resolve_persona_key("filter")  # → "engineer"
key = resolve_persona_key("merge")   # → "merger"
key = resolve_persona_key("analyze") # → "analyst"
```

---

## builder.py — system prompt 조합

**위치:** `core/prompts/builder.py`

```python
def build_system_prompt(
    files_info: list[dict],
    intent: str = "query",
    compact: bool = False,
    last_result_info: dict | None = None,
    recent_messages: list[dict] | None = None,
    persona_key: str | None = None,  # None = intent 자동 결정
) -> str:
    _key = persona_key or resolve_persona_key(intent)
    p = get_persona(_key) or get_persona("analyst")
    persona = p["system_prompt"]
    # ... 파일 정보, 예시, CODE_RULES 조합
```

`persona_key`를 넘기면 intent 무관하게 해당 페르소나 고정.  
`None`이면 intent → persona 자동 매핑.

---

## 채팅 페이지 — 페르소나 선택기

**위치:** `pages/0_채팅.py`

파일 pills 바로 아래에 페르소나 pills 한 줄이 표시됩니다.

```
[4예실대비표.xlsx] [5예실대비표.xlsx]                        2/3
[자동] [데이터 분석가] [데이터 엔지니어] [데이터 병합 전문가]  페르소나
```

- **자동** (기본): 질문 intent를 분석해서 페르소나 자동 결정
- **직접 선택**: intent 무관하게 해당 페르소나 고정

선택된 페르소나 키는 `st.session_state.selected_persona_key`에 저장됩니다.

---

## 페르소나 관리 UI 흐름

```mermaid
flowchart TD
    Entry["🎭 페르소나 탭 진입"] --> List["페르소나 목록 표시"]

    List --> Preset["프리셋 카드\nanalyst / engineer / merger"]
    List --> Custom["커스텀 카드"]
    List --> NewBtn["+ 새 페르소나 버튼"]

    Preset -->|편집 클릭| EditForm["편집 폼\n모든 필드 수정 가능"]
    Preset -->|복제 클릭| DupForm["복제 폼\n새 키 + 이름 입력"]

    Custom -->|편집 클릭| EditForm
    Custom -->|복제 클릭| DupForm
    Custom -->|삭제 클릭| Del["✅ personas.json에서 제거"]

    NewBtn --> CreateForm["생성 폼\n이름 / 키 / About\nResponse style / System Prompt\n자동 적용 intent 선택"]
    CreateForm -->|System Prompt 비워두면| AutoGen["About + Response style로\n자동 생성"]
    AutoGen --> Save
    CreateForm -->|직접 입력| Save["💾 personas.json에 저장\nst.rerun()"]
    EditForm -->|저장| Save
    DupForm -->|복제| Save
```

---

## 전체 Prompt 처리 흐름

```mermaid
flowchart TD
    Input["💬 사용자 입력\n'집행률 분석해줘'"]
    Intent["1. intent 분류\ndetect_intent() → 'analyze'"]
    Decision{"2. 페르소나 결정"}
    Auto["resolve_persona_key('analyze')\n→ 'analyst'"]
    Manual["pills에서 직접 선택한 키"]
    Build["3. system prompt 조합\nbuilder.py"]
    Parts["페르소나 system_prompt\n+ 파일 정보 (컬럼·결측치·통계)\n+ 이전 대화 맥락\n+ CODE_RULES"]
    Augment["4. user prompt 보강\naugment_user_prompt()\n→ 컬럼명·결측치 자동 주입"]
    LLM["5. LLM 호출 streaming"]
    Response["6. 응답 표시"]
    Followup["7. 후속 질문 3개 자동 생성\n_generate_suggestions()"]

    Input --> Intent
    Intent --> Decision
    Decision -->|자동 모드| Auto
    Decision -->|수동 모드| Manual
    Auto --> Build
    Manual --> Build
    Build --> Parts
    Parts --> Augment
    Augment --> LLM
    LLM --> Response
    Response --> Followup
```

---

## 커스텀 페르소나 System Prompt 작성 팁

```markdown
## 역할
당신은 [역할]입니다. [핵심 목적]이 핵심 역할입니다.

## 말투와 태도
- [구체적인 행동 지침]
- 이모지를 헤더나 항목 앞에 붙이지 마세요.
- "다음 단계 제안" 섹션을 응답 안에 직접 작성하지 마세요.

## 작업 방법론
1. 요청이 모호하면 → [어떻게 확인할지]
2. 의도가 명확하면 → [어떻게 처리할지]
3. 파일이 없으면 → 업로드 안내 후 멈추기
```

**피해야 할 것:**
- 너무 긴 역할 설명 (3~5줄이면 충분)
- 이미 CODE_RULES에 있는 내용 중복 작성
- 특정 파일명·컬럼명 하드코딩 (범용성 감소)
