"""채팅 페이지 레이아웃 — 고정 입력창이 결과를 가리지 않도록."""
from __future__ import annotations

import streamlit as st

# 고정 chat_input 높이 + 여유 (px)
_CHAT_INPUT_CLEARANCE = "6.5rem"


def apply_chat_layout_styles() -> None:
    """하단 고정 chat_input과 메인 콘텐츠 겹침 방지."""
    st.markdown(
        f"""
        <style>
        [data-testid="stMainBlockContainer"] {{
            padding-bottom: {_CHAT_INPUT_CLEARANCE} !important;
        }}
        [data-testid="stBottomBlockContainer"] {{
            background: var(--background-color, #ffffff);
            border-top: 1px solid rgba(49, 51, 63, 0.12);
            box-shadow: 0 -6px 16px rgba(0, 0, 0, 0.06);
            padding-top: 0.35rem;
        }}
        [data-testid="stChatInput"] {{
            max-width: 100%;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def chat_input_spacer() -> None:
    """스크롤 맨 아래에서도 마지막 블록이 입력창에 가려지지 않게."""
    st.markdown(
        f'<div aria-hidden="true" style="height:{_CHAT_INPUT_CLEARANCE};"></div>',
        unsafe_allow_html=True,
    )
