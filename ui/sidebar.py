"""사이드바 렌더링."""
from __future__ import annotations

import streamlit as st

from services.export import to_markdown
from ui.quality_report import load_files_info, render_compact_quality
from services.file_manager import (
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
from core.llm_client import GEMINI_MODELS, OPENAI_MODELS, list_ollama_models
from core.prompt_builder import (
    _INTENT_LABEL,
    augment_user_prompt,
    build_system_prompt,
    collect_files_info,
    detect_intent,
)


def render_sidebar() -> None:
    with st.sidebar:
        st.title("📊 Excel AI Platform")
        st.caption("엑셀/CSV 파일을 업로드하고 AI와 대화하세요")

        # ── AI 모델 설정 ──────────────────────────────────────────────────────
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

        # ── 파일 관리 ─────────────────────────────────────────────────────────
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

        files = list_files()
        if files:
            for fname in files:
                col_name, col_del = st.columns([5, 1])
                with col_name:
                    info = get_file_info(fname)
                    if info:
                        sheet_count = info.get("sheet_count", 0)
                        sheet_warn = f"  ⚠ {sheet_count} sheets" if sheet_count > 1 else ""
                        st.caption(f"📄 {fname}{sheet_warn}")
                        if sheet_count > 1:
                            names = ", ".join(info.get("sheet_names", [])[:3])
                            st.caption(f"  첫 번째만 읽힘 ({names}{'...' if sheet_count > 3 else ''})")
                        st.caption(
                            f"{info['rows']}행 × {info['columns']}열  |  {info['size_kb']} KB"
                        )
                        if info.get("used_range"):
                            st.caption(f"↳ {info['used_range']}")
                    else:
                        st.caption(f"📄 {fname}")
                with col_del:
                    if st.button("✕", key=f"del_{fname}", help="파일 삭제"):
                        delete_file(fname)
                        st.rerun()

            preview_target = st.selectbox(
                "파일 미리보기", ["선택하세요..."] + files, key="preview_select"
            )
            if preview_target and preview_target != "선택하세요...":
                df_preview = preview_file(preview_target)
                if df_preview is not None:
                    st.dataframe(df_preview, use_container_width=True, height=200)
                # 선택된 파일의 품질 요약
                all_info = load_files_info(tuple(files))
                fi = next((f for f in all_info if f["name"] == preview_target), None)
                if fi:
                    render_compact_quality(fi)
        else:
            st.caption("업로드된 파일이 없습니다.")

        st.divider()

        # ── 결과 파일 ─────────────────────────────────────────────────────────
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

        # ── 채팅 컨트롤 ───────────────────────────────────────────────────────
        col_new, col_exp = st.columns(2)
        with col_new:
            if st.button("새 대화", use_container_width=True):
                st.session_state.messages = []
                st.session_state.exec_results = {}
                st.session_state.last_result = None
                st.session_state.result_history = []
                st.session_state.last_intent = None
                st.session_state.suggestions = {}
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

        # ── 프롬프트 디버그 ───────────────────────────────────────────────────
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
