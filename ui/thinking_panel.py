"""Thinking process 접이식 패널 컴포넌트."""
from __future__ import annotations

import streamlit as st

from core.pipeline import PipelineStage, PipelineState

_STAGE_LABELS: dict[PipelineStage, tuple[str, str]] = {
    PipelineStage.INTENT:         ("Intent 분류",   "🎯"),
    PipelineStage.PERSONA:        ("Persona 결정",  "🎭"),
    PipelineStage.PROMPT_ENHANCE: ("Prompt 보강",   "✨"),
    PipelineStage.LLM_THINKING:   ("LLM 응답",      "🤖"),
    PipelineStage.EXECUTING:      ("코드 실행",      "⚙️"),
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
        c1.markdown(
            f"**Intent**  \n"
            f'<span style="background:#EFF6FF;color:#1D4ED8;padding:2px 8px;'
            f'border-radius:4px;font-size:13px;">{state.intent} ({intent_ko})</span>',
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"**Persona**  \n"
            f'<span style="background:#F0FDF4;color:#15803D;padding:2px 8px;'
            f'border-radius:4px;font-size:13px;">{state.persona_name}</span>',
            unsafe_allow_html=True,
        )
        model_label = state.model_name or "-"
        c3.markdown(
            f"**Model**  \n"
            f'<span style="background:#FDF4FF;color:#7E22CE;padding:2px 8px;'
            f'border-radius:4px;font-size:13px;">{model_label} via {state.provider}</span>',
            unsafe_allow_html=True,
        )

        st.divider()

        # ── 단계별 타이밍 바 (위로 이동) ──
        st.caption("처리 단계")
        for s in state.stages:
            label, icon = _STAGE_LABELS.get(s.stage, (s.stage.value, ""))
            pct = (s.duration_ms / total_ms) if total_ms > 0 else 0

            tc1, tc2, tc3 = st.columns([3, 5, 1])
            tc1.markdown(f"{icon} {label}")
            tc2.progress(min(pct, 1.0))
            if s.duration_ms >= 1000:
                tc3.markdown(f"**{s.duration_ms / 1000:.1f}s**")
            else:
                tc3.markdown(f"**{s.duration_ms}ms**")

        st.markdown(f"**총 소요: {total_s:.2f}초**")

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
