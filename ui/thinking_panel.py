"""Thinking process 접이식 패널 컴포넌트."""
from __future__ import annotations

import streamlit as st

from core.execution.pipeline import PipelineStage, PipelineState

_STAGE_LABELS: dict[PipelineStage, tuple[str, str]] = {
    PipelineStage.INTENT:         ("Intent 분류",   "🎯"),
    PipelineStage.PERSONA:        ("Persona 결정",  "🎭"),
    PipelineStage.PROMPT_ENHANCE: ("Prompt 보강",   "✨"),
    PipelineStage.LLM_THINKING:   ("LLM 응답",      "🤖"),
    PipelineStage.EXECUTING:      ("도구 실행",      "🔧"),
}

_TOOL_LABEL: dict[str, str] = {
    "get_row_count":   "행 수 조회",
    "analyze_missing": "결측치 분석",
    "get_profile":     "컬럼 프로파일",
    "aggregate_data":  "집계 (합계·평균)",
    "filter_rows":     "필터",
    "sort_rows":       "정렬",
    "merge_files":       "파일 병합",
    "merge_same_format": "동일 양식 통합",
    "create_chart":      "차트 생성",
}

_INTENT_KO: dict[str, str] = {
    "analyze":   "분석",
    "query":     "조회",
    "filter":    "필터",
    "aggregate": "집계",
    "transform": "변환",
    "merge":     "병합",
    "export":    "저장",
}


def render_thinking_panel(state: PipelineState) -> None:
    """응답 아래 접이식 Thinking process 패널."""
    total_ms = state.get_total_duration_ms()
    total_s = total_ms / 1000

    with st.expander(f"🧠 Thinking process — {total_s:.1f}초", expanded=False):

        # ── 상단 뱃지 행 ──
        c1, c2, c3 = st.columns(3)
        intent_ko = _INTENT_KO.get(state.intent, state.intent)
        mode_colors = {
            "llm":  "#FEF9C3;color:#854D0E",
            "code": "#EFF6FF;color:#1D4ED8",
            "tool": "#F0FDF4;color:#15803D",
        }
        mode_color = mode_colors.get(state.mode, "#EFF6FF;color:#1D4ED8")

        # tool 모드면 tool 이름 + confidence 추가 표시
        tool_badge = ""
        conf = state.task_config.get("confidence", 0.0)
        if state.mode == "tool":
            tool_key  = state.task_config.get("tool", "")
            tool_disp = _TOOL_LABEL.get(tool_key, tool_key) if tool_key else "-"
            conf_pct  = int(conf * 100)
            conf_color = "#BBF7D0;color:#15803D" if conf >= 0.85 else "#FEF9C3;color:#854D0E"
            tool_badge = (
                f' &nbsp;<span style="background:#E0F2FE;color:#0369A1;padding:2px 7px;'
                f'border-radius:4px;font-size:12px;">🔧 {tool_disp}</span>'
                f' <span style="background:{conf_color};padding:2px 5px;'
                f'border-radius:4px;font-size:11px;">{conf_pct}%</span>'
            )

        c1.markdown(
            f"**Intent**  \n"
            f'<span style="background:#EFF6FF;color:#1D4ED8;padding:2px 8px;'
            f'border-radius:4px;font-size:13px;">{state.intent} ({intent_ko})</span> '
            f'<span style="background:{mode_color};padding:2px 6px;'
            f'border-radius:4px;font-size:12px;">{state.mode}</span>'
            f'{tool_badge}',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"**Persona**  \n"
            f'<span style="background:#F0FDF4;color:#15803D;padding:2px 8px;'
            f'border-radius:4px;font-size:13px;">{state.persona_name}</span>',
            unsafe_allow_html=True,
        )
        model_label = state.model_name or ("(tool)" if state.mode == "tool" else "-")
        c3.markdown(
            f"**Model**  \n"
            f'<span style="background:#FDF4FF;color:#7E22CE;padding:2px 8px;'
            f'border-radius:4px;font-size:13px;">{model_label} via {state.provider or "tool"}</span>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── 단계별 타이밍 바 ──
        st.caption("처리 단계")
        for s in state.stages:
            label, icon = _STAGE_LABELS.get(s.stage, (s.stage.value, ""))
            pct = (s.duration_ms / total_ms) if total_ms > 0 else 0

            # EXECUTING 단계에 tool 정보 인라인 표시
            if s.stage == PipelineStage.EXECUTING and s.details.get("tool"):
                tl = s.details.get("tool_label", s.details["tool"])
                conf = int(s.details.get("confidence", 0) * 100)
                label = f"{label}: **{tl}** ({conf}%)"

            tc1, tc2, tc3 = st.columns([3, 5, 1])
            tc1.markdown(f"{icon} {label}")
            tc2.progress(min(pct, 1.0))
            if s.duration_ms >= 1000:
                tc3.markdown(f"**{s.duration_ms / 1000:.1f}s**")
            else:
                tc3.markdown(f"**{s.duration_ms}ms**")

        st.markdown(f"**총 소요: {total_s:.2f}초**")

        # ── Tool 실행 상세 (EXECUTING 단계가 있을 때만) ──
        exec_stage = next(
            (s for s in state.stages if s.stage == PipelineStage.EXECUTING), None
        )
        if exec_stage and exec_stage.details.get("tool"):
            with st.expander("🔧 Tool 실행 상세", expanded=False):
                d = exec_stage.details
                ec1, ec2, ec3 = st.columns(3)
                ec1.metric("도구",   d.get("tool_label", d.get("tool", "-")))
                ec2.metric("신뢰도", f"{int(d.get('confidence', 0) * 100)}%")
                ec3.metric("소요",
                    f"{exec_stage.duration_ms / 1000:.2f}s"
                    if exec_stage.duration_ms >= 1000
                    else f"{exec_stage.duration_ms}ms"
                )
                files = d.get("files", [])
                if files:
                    st.caption("대상 파일: " + ", ".join(str(f) for f in files if f))
                if d.get("result_label"):
                    cached_tag = " ⚡ 캐시" if d.get("cached") else ""
                    st.caption(f"결과: {d['result_label']} ({d.get('result_type', '')}){cached_tag}")

        st.divider()

        # ── Prompt 보강 비교 ──
        enhance_stage = next(
            (s for s in state.stages if s.stage == PipelineStage.PROMPT_ENHANCE), None
        )
        if enhance_stage and enhance_stage.details.get("was_enhanced"):
            with st.expander("Prompt 보강 내용 보기", expanded=False):
                pcol1, pcol2 = st.columns(2)
                with pcol1:
                    st.caption("원본")
                    st.code(state.user_prompt, language="text")
                with pcol2:
                    st.caption("보강 후")
                    st.code(state.augmented_prompt, language="text")

        # ── 토큰 추정 + System prompt ──
        with st.expander("System prompt 전문 보기", expanded=False):
            st.code(state.system_prompt, language="markdown")

        st.caption(
            f"System prompt: **~{state.system_prompt_token_est:,}** 토큰   "
            f"| 응답: **~{state.response_token_est:,}** 토큰"
        )

        # ── 세션 실행 체인 (2턴 이상일 때만) ──
        _hist = st.session_state.get("session_history")
        if _hist is not None and _hist.total() >= 2:
            _chain = _hist.chain_str()
            if _chain:
                st.caption(f"🔗 세션 체인: {_chain}")
