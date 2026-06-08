"""앱 전역 공유 헬퍼 — 세션 상태 초기화, LLM 클라이언트 생성 등."""
from __future__ import annotations

import streamlit as st

from core.chat_history import load_chat, new_chat_id
from core.execution.pipeline import PipelineState
from core.llm.llm_client import GEMINI_MODELS, OPENAI_MODELS, LLMClient, get_client

# 코드 생성이 필요한 의도 — 코드 특화 모델로 라우팅
_CODE_INTENTS = frozenset({"filter", "aggregate", "transform", "merge", "export"})

_DEFAULTS: dict = {
    "messages": [],
    "exec_results": {},
    "provider": "Ollama",
    "ollama_model": "gemma3:27b",
    "ollama_code_model": "",   # "" → 대화 모델과 동일
    "gemini_key": "",
    "openai_key": "",
    "ollama_host": "http://localhost:11434",
    "last_result": None,
    "result_history": [],
    "last_intent": None,
    "pending_prompt": None,
    "suggestions": {},
    "current_chat_id": "",
    "selected_sheets": {},        # fname → sheet_name
    "selected_files": [],         # 채팅에서 활성화된 파일 목록
    "selected_persona_key": None, # None = intent 자동 결정
    "llm_temperature": 0.7,
    "llm_max_tokens": 4096,
    "compare_results": None,
    "pipeline_states": {},   # {msg_idx: PipelineState}
    "dsl_results":     {},   # {msg_idx: {intent, pipeline, exec, summary, dt_ms, error, ...}}
}


def init_session_state() -> None:
    """모든 페이지 최상단에서 호출 — 세션 상태 기본값 보장."""
    for k, v in _DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if "session_history" not in st.session_state:
        from core.execution.pipeline import SessionHistory
        st.session_state.session_history = SessionHistory()


def restore_chat(chat_id: str) -> bool:
    """디스크에서 채팅을 로드해 세션 상태에 복원.

    messages, pipeline_states를 채우고 부수 상태(exec_results, last_result,
    suggestions, session_history)를 초기화한다. chat_id가 비었거나 파일이
    없으면 False 반환.
    """
    if not chat_id:
        return False
    loaded = load_chat(chat_id)
    if not loaded:
        return False

    st.session_state.messages         = loaded
    st.session_state.current_chat_id  = chat_id
    st.session_state.exec_results     = {}
    st.session_state.last_result      = None
    st.session_state.result_history   = []
    st.session_state.last_intent      = None
    st.session_state.suggestions      = {}

    from core.execution.pipeline import SessionHistory
    st.session_state.session_history = SessionHistory()

    restored: dict[int, PipelineState] = {}
    restored_dsl: dict[int, dict] = {}
    for i, m in enumerate(loaded):
        if not isinstance(m, dict):
            continue
        p = m.get("pipeline")
        if p:
            try:
                restored[i] = PipelineState.from_dict(p)
            except Exception:
                pass
        # DSL 결과는 dict(JSON)로 그대로 보관 — dataframe은 직렬화 불가하므로
        # exec.value(table dict) / log / 메타만 저장됨 (Step 2.3.4 참조)
        d = m.get("dsl_result")
        if d and isinstance(d, dict):
            restored_dsl[i] = d
    st.session_state.pipeline_states = restored
    st.session_state.dsl_results = restored_dsl
    return True


def start_new_chat() -> str:
    """새 채팅 ID를 발급하고 세션을 초기화한다. 새 chat_id 반환."""
    cid = new_chat_id()
    st.session_state.messages         = []
    st.session_state.current_chat_id  = cid
    st.session_state.exec_results     = {}
    st.session_state.pipeline_states  = {}
    st.session_state.dsl_results      = {}
    st.session_state.last_result      = None
    st.session_state.result_history   = []
    st.session_state.last_intent      = None
    st.session_state.suggestions      = {}

    from core.execution.pipeline import SessionHistory
    st.session_state.session_history = SessionHistory()
    return cid


def get_llm_client(
    intent: str = "",
    force_code: bool = False,
) -> tuple[LLMClient | None, str | None]:
    """현재 세션 상태에서 LLM 클라이언트를 생성한다.

    Ollama 환경에서 intent가 코드 생성 범주이거나 force_code=True이면
    ollama_code_model을 우선 사용한다 (설정된 경우에만).

    Returns:
        (client, None)      — 성공
        (None, 오류메시지)  — 실패
    """
    temperature = st.session_state.get("llm_temperature", 0.7)
    max_tokens  = st.session_state.get("llm_max_tokens", 4096)

    p = st.session_state.provider
    if p == "Ollama":
        use_code = force_code or intent in _CODE_INTENTS
        code_model = st.session_state.get("ollama_code_model", "")
        model = (code_model if use_code and code_model else st.session_state.ollama_model)
        if not model:
            return None, "Ollama 모델을 선택해 주세요."
        client = get_client(
            "Ollama", model,
            ollama_host=st.session_state.ollama_host,
            temperature=temperature, max_tokens=max_tokens,
        )
        if client is None:
            return None, "Ollama 연결에 실패했습니다. Ollama가 실행 중인지 확인하세요."
        return client, None
    elif p == "Gemini":
        key = st.session_state.gemini_key.strip()
        model = st.session_state.get("gemini_model", GEMINI_MODELS[0])
        if not key:
            return None, "Gemini API 키를 입력해 주세요."
        return get_client("Gemini", model, api_key=key, temperature=temperature, max_tokens=max_tokens), None
    elif p == "OpenAI":
        key = st.session_state.openai_key.strip()
        model = st.session_state.get("openai_model", OPENAI_MODELS[0])
        if not key:
            return None, "OpenAI API 키를 입력해 주세요."
        return get_client("OpenAI", model, api_key=key, temperature=temperature, max_tokens=max_tokens), None
    return None, "지원하지 않는 프로바이더입니다."


def get_embedder():
    """현재 세션 설정 기반 Embedder 반환. API key 없으면 KeywordEmbedder fallback."""
    from core.rag.embedder import GeminiEmbedder, KeywordEmbedder, OpenAIEmbedder

    p = st.session_state.provider
    if p == "OpenAI":
        key = st.session_state.get("openai_key", "").strip()
        if key:
            return OpenAIEmbedder(api_key=key)
    elif p == "Gemini":
        key = st.session_state.get("gemini_key", "").strip()
        if key:
            return GeminiEmbedder(api_key=key)
    return KeywordEmbedder()
