"""Excel AI Platform — Streamlit 기반 대화형 엑셀 처리 앱.
지원 모델: Ollama (로컬), Google Gemini, OpenAI GPT.
"""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from utils.code_executor import execute
from utils.export import to_markdown
from utils.file_manager import (
    RESULT_DIR,
    delete_file,
    delete_result,
    get_file_info,
    list_files,
    list_results,
    preview_file,
    read_file,
    save_uploaded,
)
from utils.llm_client import (
    GEMINI_MODELS,
    OPENAI_MODELS,
    get_client,
    list_ollama_models,
)
from utils.prompt_builder import (
    augment_user_prompt,
    build_system_prompt,
    collect_files_info,
    detect_intent,
    _INTENT_LABEL,
)

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Excel AI Platform",
    page_icon="📊",
    layout="wide",
)

# ── Session state ──────────────────────────────────────────────────────────────

defaults = {
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
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ────────────────────────────────────────────────────────────────────

# 의도별 배지 색상 (dark theme 기준)
_INTENT_BADGE_COLOR: dict[str, tuple[str, str]] = {
    "merge":     ("#1e3a5f", "#7dd3fc"),   # 파란
    "filter":    ("#14532d", "#86efac"),   # 초록
    "aggregate": ("#7c2d12", "#fdba74"),   # 주황
    "transform": ("#713f12", "#fde047"),   # 노랑
    "analyze":   ("#4a1d96", "#d8b4fe"),   # 보라
    "export":    ("#1f2937", "#9ca3af"),   # 회색
    "query":     ("#1f2937", "#9ca3af"),   # 회색
}


def intent_badge_html(intent: str, label: str) -> str:
    bg, fg = _INTENT_BADGE_COLOR.get(intent, ("#1f2937", "#9ca3af"))
    return (
        f'<span style="background:{bg};color:{fg};'
        f'padding:2px 10px;border-radius:12px;'
        f'font-size:12px;font-weight:600;">'
        f'🏷 {label}</span>'
    )


def extract_code_blocks(text: str) -> list[str]:
    return re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL)


def get_llm_client():
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
        client = get_client("Gemini", model, api_key=key)
        return client, None
    elif p == "OpenAI":
        key = st.session_state.openai_key.strip()
        model = st.session_state.get("openai_model", OPENAI_MODELS[0])
        if not key:
            return None, "OpenAI API 키를 입력해 주세요."
        client = get_client("OpenAI", model, api_key=key)
        return client, None
    return None, "지원하지 않는 프로바이더입니다."


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("📊 Excel AI Platform")
    st.caption("엑셀/CSV 파일을 업로드하고 AI와 대화하세요")

    # ── AI Provider ─────────────────────────────────────────────────────────
    st.subheader("AI 모델 설정")

    provider = st.selectbox(
        "프로바이더",
        ["Ollama", "Gemini", "OpenAI"],
        index=["Ollama", "Gemini", "OpenAI"].index(st.session_state.provider),
        key="provider",
    )

    if provider == "Ollama":
        ollama_host = st.text_input(
            "Ollama Host",
            value=st.session_state.ollama_host,
            key="ollama_host",
        )
        with st.spinner("Ollama 모델 목록 조회 중..."):
            ollama_models = list_ollama_models(ollama_host)
        if ollama_models:
            st.selectbox("모델 선택", ollama_models, key="ollama_model")
        else:
            st.warning("Ollama 모델을 찾을 수 없습니다. Ollama가 실행 중인지 확인하세요.")
            st.session_state.ollama_model = None

    elif provider == "Gemini":
        st.text_input(
            "Gemini API 키",
            type="password",
            placeholder="AIza...",
            key="gemini_key",
        )
        st.selectbox("모델", GEMINI_MODELS, key="gemini_model")

    elif provider == "OpenAI":
        st.text_input(
            "OpenAI API 키",
            type="password",
            placeholder="sk-...",
            key="openai_key",
        )
        st.selectbox("모델", OPENAI_MODELS, key="openai_model")

    st.divider()

    # ── File upload ──────────────────────────────────────────────────────────
    st.subheader("파일 관리")

    uploaded = st.file_uploader(
        "엑셀 / CSV 업로드",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if uploaded:
        for f in uploaded:
            save_uploaded(f)
        st.success(f"{len(uploaded)}개 파일 업로드 완료")

    # ── File list ────────────────────────────────────────────────────────────
    files = list_files()
    if files:
        for fname in files:
            col_name, col_del = st.columns([5, 1])
            with col_name:
                info = get_file_info(fname)
                if info:
                    # 멀티 시트 경고 인라인
                    sheet_count = info.get("sheet_count", 0)
                    sheet_warn = (
                        f"  ⚠ {sheet_count} sheets"
                        if sheet_count > 1 else ""
                    )
                    st.caption(f"📄 {fname}{sheet_warn}")
                    if sheet_count > 1:
                        names = ", ".join(info.get("sheet_names", [])[:3])
                        st.caption(f"  첫 번째만 읽힘 ({names}{'...' if sheet_count > 3 else ''})")
                    st.caption(
                        f"{info['rows']}행 × {info['columns']}열  |  "
                        f"{info['size_kb']} KB"
                    )
                    if info.get("used_range"):
                        st.caption(f"↳ {info['used_range']}")
                else:
                    st.caption(f"📄 {fname}")
            with col_del:
                if st.button("✕", key=f"del_{fname}", help="파일 삭제"):
                    delete_file(fname)
                    st.rerun()

        # Preview
        preview_target = st.selectbox(
            "파일 미리보기", ["선택하세요..."] + files, key="preview_select"
        )
        if preview_target and preview_target != "선택하세요...":
            df_preview = preview_file(preview_target)
            if df_preview is not None:
                st.dataframe(df_preview, use_container_width=True, height=200)
    else:
        st.caption("업로드된 파일이 없습니다.")

    st.divider()

    # ── Results ──────────────────────────────────────────────────────────────
    result_files = list_results()
    if result_files:
        st.subheader("결과 파일")
        for fname in result_files:
            col_n, col_dl, col_del = st.columns([3, 1, 1])
            with col_n:
                st.caption(f"📊 {fname}")
            with col_dl:
                fpath = RESULT_DIR / fname
                st.download_button(
                    "⬇",
                    data=fpath.read_bytes(),
                    file_name=fname,
                    key=f"dl_{fname}",
                    help="다운로드",
                )
            with col_del:
                if st.button("✕", key=f"del_res_{fname}", help="결과 삭제"):
                    delete_result(fname)
                    st.rerun()
        st.divider()

    # ── Chat controls ────────────────────────────────────────────────────────
    col_new, col_exp = st.columns(2)
    with col_new:
        if st.button("새 대화", use_container_width=True):
            st.session_state.messages = []
            st.session_state.exec_results = {}
            st.session_state.last_result = None
            st.session_state.result_history = []
            st.session_state.last_intent = None
            st.rerun()
    with col_exp:
        if st.session_state.messages:
            md = to_markdown(st.session_state.messages)
            st.download_button(
                "내보내기",
                data=md,
                file_name="chat_export.md",
                mime="text/markdown",
                use_container_width=True,
            )

    st.divider()

    # ── 프롬프트 디버그 토글 ─────────────────────────────────────────────────
    with st.expander("보강된 프롬프트 보기 (디버그)", expanded=False):
        debug_input = st.text_area(
            "테스트할 입력",
            placeholder="예: 매출 기준으로 필터해줘",
            height=68,
            key="debug_input",
        )
        if debug_input:
            _fi = collect_files_info(list_files, read_file)
            _intent = detect_intent(debug_input)
            st.caption(f"감지된 의도: **{_INTENT_LABEL.get(_intent, _intent)}**")
            st.subheader("사용자 프롬프트 → 보강 후")
            st.code(augment_user_prompt(debug_input, _fi), language="text")
            st.subheader("시스템 프롬프트 (동적 조합)")
            st.code(build_system_prompt(_fi, _intent), language="text")

# ── Main chat area ─────────────────────────────────────────────────────────────

st.header("AI와 대화하기")

if not list_files():
    st.info("왼쪽 사이드바에서 엑셀 또는 CSV 파일을 업로드하면 AI가 데이터를 분석하고 처리합니다.")


def render_code_controls(msg_idx: int, content: str):
    """코드 실행 버튼 또는 실행 결과를 렌더링."""
    exec_result = st.session_state.exec_results.get(msg_idx)

    if exec_result is not None:
        if exec_result.success:
            if exec_result.output:
                st.code(exec_result.output, language="text")
            if exec_result.result_df is not None:
                st.dataframe(exec_result.result_df, use_container_width=True)
            for sfname in exec_result.saved_files:
                fpath = RESULT_DIR / sfname
                if fpath.exists():
                    st.download_button(
                        f"⬇ {sfname} 다운로드",
                        data=fpath.read_bytes(),
                        file_name=sfname,
                        key=f"dl_exec_{sfname}_{msg_idx}",
                    )
            st.success("코드 실행 완료")
        else:
            st.error(f"실행 오류:\n{exec_result.error}")
        return

    code_blocks = extract_code_blocks(content)
    if code_blocks:
        if st.button("▶ 코드 실행", key=f"exec_{msg_idx}"):
            with st.spinner("실행 중..."):
                result = execute(
                    code_blocks[0],
                    last_result=st.session_state.last_result,
                )
            st.session_state.exec_results[msg_idx] = result
            if result.success and result.result_df is not None:
                st.session_state.last_result = result.result_df
                st.session_state.result_history.append(result.result_df)
            st.rerun()


# Render chat history
for idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        # 사용자에게는 보강 전 원본 표시
        display_content = msg.get("display", msg["content"])
        st.markdown(display_content)
        # 인텐트 배지 (사용자 메시지에만)
        if msg["role"] == "user" and msg.get("intent"):
            label = _INTENT_LABEL.get(msg["intent"], msg["intent"])
            st.markdown(
                intent_badge_html(msg["intent"], label),
                unsafe_allow_html=True,
            )
        if msg["role"] == "assistant":
            render_code_controls(idx, msg["content"])

# ── Chat input ─────────────────────────────────────────────────────────────────

if prompt := st.chat_input("파일 분석, 병합, 필터링 등 무엇이든 물어보세요..."):
    # ── 1. 의도 감지 ──────────────────────────────────────────────────────────
    files_info = collect_files_info(list_files, read_file)
    intent = detect_intent(prompt)
    st.session_state.last_intent = intent

    # 직전 결과 메타 (있을 때만)
    _lr = st.session_state.last_result
    last_result_info: dict | None = None
    if _lr is not None:
        if isinstance(_lr, pd.DataFrame):
            last_result_info = {
                "rows": len(_lr),
                "columns": len(_lr.columns),
                "col_names": list(_lr.columns.astype(str)),
            }

    # ── 2. 사용자 프롬프트 보강 ───────────────────────────────────────────────
    augmented_prompt = augment_user_prompt(prompt, files_info, last_result_info)

    # 화면에는 원본, LLM에는 보강된 메시지 + intent 저장
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

    client, error_msg = get_llm_client()

    if error_msg:
        with st.chat_message("assistant"):
            st.error(error_msg)
    else:
        # ── 3. 동적 시스템 프롬프트 조합 ─────────────────────────────────────
        # Ollama 소형 모델(7b/8b 이하)은 compact 모드로 프롬프트 단축
        selected_model = st.session_state.get("ollama_model", "") or ""
        is_compact = st.session_state.provider == "Ollama" and any(
            tag in selected_model.lower() for tag in ("7b", "8b", "3b", "1b", "mini")
        )
        system = build_system_prompt(
            files_info, intent, compact=is_compact,
            last_result_info=last_result_info,
        )

        with st.chat_message("assistant"):
            try:
                response = st.write_stream(
                    client.chat_stream(st.session_state.messages, system)
                )
            except Exception as e:
                response = f"오류가 발생했습니다: {e}"
                st.error(response)

        msg_idx = len(st.session_state.messages)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()
