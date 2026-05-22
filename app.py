"""Excel AI Platform — 진입점."""
from __future__ import annotations

import streamlit as st

from ui.helpers import init_session_state
from ui.sidebar import render_sidebar

st.set_page_config(
    page_title="Excel AI Platform",
    page_icon="📊",
    layout="wide",
)

init_session_state()
render_sidebar()

pg = st.navigation([
    st.Page("pages/0_채팅.py",    title="AI 채팅",    icon="💬"),
    st.Page("pages/1_파일관리.py", title="파일관리",   icon="📂"),
    st.Page("pages/3_페르소나.py", title="페르소나",   icon="🎭"),
    st.Page("pages/2_설정.py",    title="설정",       icon="⚙️"),
])
pg.run()
