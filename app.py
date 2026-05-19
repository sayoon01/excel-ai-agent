"""Excel AI Platform — 진입점.
지원 모델: Ollama (로컬), Google Gemini, OpenAI GPT.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.file_manager import list_files
from core.code_executor import execute
from core.llm_client import GEMINI_MODELS, OPENAI_MODELS, get_client
from core.prompt_builder import (
    _INTENT_LABEL,
    augment_user_prompt,
    build_system_prompt,
    detect_intent,
)
from ui.components import intent_badge_html
from ui.chat_view import extract_code_blocks, render_chat_history, render_last_result_banner
from ui.quality_report import load_files_info
from ui.sidebar import render_sidebar

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Excel AI Platform",
    page_icon="📊",
    layout="wide",
)

# ── Session state ──────────────────────────────────────────────────────────────

_DEFAULTS = {
    "messages": [],
    "exec_results": {},
    "provider": "Ollama",
    "ollama_model": None,
    "gemini_key": "",
    "openai_key": "",
    "ollama_host": "http://localhost:11434",
    "last_result": None,
    "result_history": [],
    "last_intent": None,
    "pending_prompt": None,
    "suggestions": {},
    "correction_needed": {},
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── LLM 유틸 ──────────────────────────────────────────────────────────────────

_CORRECTION_SYSTEM = (
    "Python/pandas 코드 디버거입니다. 오류를 수정한 코드 블록만 반환하세요. 설명 불필요.\n"
    "환경: files(dict), pd, np, plt 주입됨. import 문 사용 불가. "
    "최종 결과는 반드시 result 변수에 저장."
)

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


def _handle_correction(msg_idx: int, code: str, error: str, attempt: int) -> None:
    """에러난 코드를 LLM에게 보내 수정 코드를 받아 재실행."""
    client, err = _get_llm_client()
    if err:
        del st.session_state.correction_needed[msg_idx]
        return

    user_question = ""
    if msg_idx > 0:
        prev = st.session_state.messages[msg_idx - 1]
        if prev["role"] == "user":
            user_question = prev.get("display", prev["content"])

    correction_msg = (
        f"원래 질문: {user_question}\n\n"
        f"실행한 코드:\n```python\n{code}\n```\n\n"
        f"오류 메시지:\n{error}\n\n수정된 코드를 제공해주세요."
    )
    try:
        raw = "".join(client.chat_stream(
            [{"role": "user", "content": correction_msg}],
            _CORRECTION_SYSTEM,
        ))
        codes = extract_code_blocks(raw)
        if not codes:
            del st.session_state.correction_needed[msg_idx]
            return

        result = execute(codes[0], last_result=st.session_state.last_result)
        result.is_corrected = True
        st.session_state.exec_results[msg_idx] = result

        if result.success:
            if result.result_df is not None:
                st.session_state.last_result = result.result_df
                st.session_state.result_history.append(result.result_df)
            del st.session_state.correction_needed[msg_idx]
        elif attempt < 2:
            st.session_state.correction_needed[msg_idx] = {
                "code": codes[0], "error": result.error, "attempt": attempt + 1,
            }
        else:
            del st.session_state.correction_needed[msg_idx]
    except Exception:
        del st.session_state.correction_needed[msg_idx]


def _get_llm_client():
    p = st.session_state.provider
    if p == "Ollama":
        model = st.session_state.ollama_model
        if not model:
            return None, "Ollama 모델을 선택해 주세요."
        client = get_client("Ollama", model, ollama_host=st.session_state.ollama_host)
        if client is None:
            return None, "Ollama 연결에 실패했습니다. Ollama가 실행 중인지 확인하세요."
        return client, None
    elif p == "Gemini":
        key = st.session_state.gemini_key.strip()
        model = st.session_state.get("gemini_model", GEMINI_MODELS[0])
        if not key:
            return None, "Gemini API 키를 입력해 주세요."
        return get_client("Gemini", model, api_key=key), None
    elif p == "OpenAI":
        key = st.session_state.openai_key.strip()
        model = st.session_state.get("openai_model", OPENAI_MODELS[0])
        if not key:
            return None, "OpenAI API 키를 입력해 주세요."
        return get_client("OpenAI", model, api_key=key), None
    return None, "지원하지 않는 프로바이더입니다."

# ── Render ─────────────────────────────────────────────────────────────────────

render_sidebar()

# ── 자동 수정 처리 ─────────────────────────────────────────────────────────────
if st.session_state.correction_needed:
    for _midx, _info in list(st.session_state.correction_needed.items()):
        with st.spinner(f"코드 오류 자동 수정 중... ({_info['attempt']}/2)"):
            _handle_correction(_midx, _info["code"], _info["error"], _info["attempt"])
    st.rerun()

st.header("AI와 대화하기")

_uploaded_files = list_files()
_files_info = load_files_info(tuple(_uploaded_files)) if _uploaded_files else []

if not _uploaded_files:
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
    intent = detect_intent(prompt)
    st.session_state.last_intent = intent

    _lr = st.session_state.last_result
    last_result_info: dict | None = None
    if _lr is not None and isinstance(_lr, pd.DataFrame):
        last_result_info = {
            "rows": len(_lr),
            "columns": len(_lr.columns),
            "col_names": list(_lr.columns.astype(str)),
        }

    augmented_prompt = augment_user_prompt(prompt, files_info, last_result_info)

    st.session_state.messages.append({
        "role": "user",
        "content": augmented_prompt,
        "display": prompt,
        "intent": intent,
    })
    with st.chat_message("user"):
        st.markdown(prompt)
        label = _INTENT_LABEL.get(intent, intent)
        st.markdown(intent_badge_html(intent, label), unsafe_allow_html=True)

    client, error_msg = _get_llm_client()

    if error_msg:
        with st.chat_message("assistant"):
            st.error(error_msg)
    else:
        selected_model = st.session_state.get("ollama_model", "") or ""
        is_compact = st.session_state.provider == "Ollama" and any(
            tag in selected_model.lower() for tag in ("7b", "8b", "3b", "1b", "mini")
        )
        system = build_system_prompt(
            files_info, intent, compact=is_compact,
            last_result_info=last_result_info,
            recent_messages=st.session_state.messages,
        )

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
                        client.chat_stream(st.session_state.messages, system)
                    )
                )
            except Exception as e:
                _typing.empty()
                response = f"오류가 발생했습니다: {e}"
                st.error(response)

        msg_idx = len(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": response})

        with st.spinner("후속 질문 생성 중..."):
            suggs = _generate_suggestions(client, prompt, response)
        if suggs:
            st.session_state.suggestions[msg_idx] = suggs

        st.rerun()
