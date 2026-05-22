"""AI 채팅 페이지."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.file_manager import list_files
from core.intent import INTENT_LABEL
from core.persona_manager import list_personas
from core.pipeline import PipelineStage
from core.pipeline_executor import parse_llm_response, run_pre_generation
from core.chat_history import new_chat_id, save_chat
from ui.components import intent_badge_html
from ui.chat_view import render_chat_history, render_last_result_banner
from ui.helpers import get_llm_client
from ui.quality_report import load_files_info

if not st.session_state.current_chat_id:
    st.session_state.current_chat_id = new_chat_id()

_SUGGESTION_SYSTEM = (
    "너는 데이터 분석 어시스턴트야. "
    "방금 나눈 대화를 보고 사용자가 자연스럽게 이어서 할 만한 후속 작업을 정확히 3개 제안해. "
    "조건:\n"
    "- 한국어, 각 항목은 한 줄, 반드시 15자 이내 (버튼에 표시되므로 짧게)\n"
    "- 번호/기호/이모지 없이 줄바꿈으로만 구분\n"
    "- '~해줘' 형태의 짧은 명령형으로 작성 (예: '결측치 제거해줘', 'Unnamed 열 삭제해줘')\n"
    "- 물음표·질문형('~까요?', '~될까요?', '~어떤') 절대 금지 — 명령형만\n"
    "- 파일은 이미 업로드되어 있으므로 파일 경로·로딩 방법을 묻는 제안 금지\n"
    "- 실제 데이터 작업(필터, 집계, 변환, 저장, 분석, 차트)에 관한 작업만"
)


def _generate_suggestions(client, user_msg: str, assistant_msg: str) -> list[str]:
    messages = [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": assistant_msg[:800]},
        {"role": "user", "content": "후속 질문 3개만 제안해줘."},
    ]
    try:
        raw = "".join(client.chat_stream(messages, _SUGGESTION_SYSTEM))
        lines = [
            line.strip().lstrip("0123456789.-•*·) ").strip()
            for line in raw.strip().splitlines()
            if line.strip()
        ]
        return [ln for ln in lines if 3 < len(ln) <= 20][:3]
    except Exception:
        return []


st.header("AI와 대화하기")

_uploaded_files = list_files()

# ── 파일 선택 pills ────────────────────────────────────────────────────────────
_PILL_KEY   = "file_selector_pills"
_KNOWN_KEY  = "known_uploaded_files"   # 이전 렌더 시점의 파일 목록

if _uploaded_files:
    _all_set  = set(_uploaded_files)
    _known    = set(st.session_state.get(_KNOWN_KEY, []))
    _truly_new = [f for f in _uploaded_files if f not in _known]

    if _PILL_KEY not in st.session_state:
        # 최초 렌더: 전체 선택
        st.session_state[_PILL_KEY] = _uploaded_files[:]
    elif _truly_new:
        # 새 파일이 업로드됨 → 현재 선택에 추가
        _cur = [f for f in st.session_state[_PILL_KEY] if f in _all_set]
        st.session_state[_PILL_KEY] = _cur + _truly_new
    else:
        # 유저 토글 또는 파일 삭제 → 삭제된 파일만 제거, 유저 선택 유지
        _cur = [f for f in st.session_state[_PILL_KEY] if f in _all_set]
        if len(_cur) != len(st.session_state[_PILL_KEY]):
            st.session_state[_PILL_KEY] = _cur

    # 현재 파일 목록 기록 (다음 렌더에서 진짜 새 파일 판별용)
    st.session_state[_KNOWN_KEY] = _uploaded_files[:]

    _col_pills, _col_count = st.columns([9, 1])
    with _col_pills:
        _selected = st.pills(
            "분석할 파일",
            options=_uploaded_files,
            selection_mode="multi",
            key=_PILL_KEY,
            label_visibility="collapsed",
        )
    with _col_count:
        _n = len(_selected) if _selected else 0
        st.caption(f"{_n} / {len(_uploaded_files)}")

    st.session_state.selected_files = list(_selected) if _selected else []

    # ── 페르소나 선택 pills ────────────────────────────────────────────────
    _personas = list_personas()
    _p_names = ["자동"] + [p["name"] for p in _personas.values()]
    _p_key_by_name = {p["name"]: k for k, p in _personas.items()}
    _PERSONA_PILL_KEY = "persona_pill_sel"
    if _PERSONA_PILL_KEY not in st.session_state:
        st.session_state[_PERSONA_PILL_KEY] = "자동"

    _col_p, _col_p_label = st.columns([9, 1])
    with _col_p:
        _sel_persona_name = st.pills(
            "페르소나",
            options=_p_names,
            selection_mode="single",
            key=_PERSONA_PILL_KEY,
            label_visibility="collapsed",
        )
    with _col_p_label:
        st.caption("페르소나")

    if _sel_persona_name and _sel_persona_name != "자동":
        st.session_state.selected_persona_key = _p_key_by_name.get(_sel_persona_name)
    else:
        st.session_state.selected_persona_key = None

    if not _selected:
        st.warning("분석할 파일을 하나 이상 선택하세요.")
        _files_info = []
    else:
        _files_info = load_files_info(tuple(_selected))
else:
    st.session_state.selected_files = []
    _files_info = []
    st.info("왼쪽 사이드바에서 엑셀 또는 CSV 파일을 업로드하면 AI가 데이터를 분석하고 처리합니다.")

render_chat_history()
render_last_result_banner()

# ── Chat input & handler ───────────────────────────────────────────────────────

_pending = st.session_state.get("pending_prompt")
if _pending:
    st.session_state.pending_prompt = None

prompt = _pending or st.chat_input("파일 분석, 병합, 필터링 등 무엇이든 물어보세요...")

if prompt:
    files_info = _files_info

    _lr = st.session_state.last_result
    last_result_info: dict | None = None
    if _lr is not None and isinstance(_lr, pd.DataFrame):
        last_result_info = {
            "rows": len(_lr),
            "columns": len(_lr.columns),
            "col_names": list(_lr.columns.astype(str)),
        }

    # ── Step 1~3: Intent / Persona / Prompt 보강 (메트릭 수집) ──
    selected_model = st.session_state.get("ollama_model", "") or ""
    is_compact = st.session_state.provider == "Ollama" and any(
        tag in selected_model.lower() for tag in ("7b", "8b", "3b", "1b", "mini")
    )
    state = run_pre_generation(
        user_prompt=prompt,
        files_info=files_info,
        last_result_info=last_result_info,
        persona_override=st.session_state.get("selected_persona_key"),
        compact=is_compact,
        recent_messages=st.session_state.messages,
    )
    st.session_state.last_intent = state.intent

    st.session_state.messages.append({
        "role": "user",
        "content": state.augmented_prompt,
        "display": prompt,
        "intent": state.intent,
    })
    with st.chat_message("user"):
        st.markdown(prompt)
        label = INTENT_LABEL.get(state.intent, state.intent)
        st.markdown(intent_badge_html(state.intent, label), unsafe_allow_html=True)

    client, error_msg = get_llm_client(intent=state.intent)

    if error_msg:
        with st.chat_message("assistant"):
            st.error(error_msg)
    else:
        # ── Step 4: LLM 호출 (메트릭 수집) ──
        state.model_name = selected_model
        state.provider = st.session_state.provider
        m_llm = state.start_stage(PipelineStage.LLM_THINKING)

        with st.chat_message("assistant"):
            _typing = st.empty()
            _typing.markdown("_답변을 생성하고 있습니다..._")

            def _stream_with_indicator(gen):
                first = True
                for chunk in gen:
                    if first:
                        _typing.empty()
                        first = False
                    yield chunk

            try:
                response = st.write_stream(
                    _stream_with_indicator(
                        client.chat_stream(st.session_state.messages, state.system_prompt)
                    )
                )
            except Exception as e:
                _typing.empty()
                response = f"오류가 발생했습니다: {e}"
                st.error(response)

        m_llm.finish()

        # ── Step 5: 응답 파싱 ──
        state = parse_llm_response(state, response)

        msg_idx = len(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.pipeline_states[msg_idx] = state
        save_chat(st.session_state.current_chat_id, st.session_state.messages)

        with st.spinner("후속 질문 생성 중..."):
            suggs = _generate_suggestions(client, prompt, response)
        if suggs:
            st.session_state.suggestions[msg_idx] = suggs

        st.rerun()
