"""페르소나 관리 Streamlit UI."""
from __future__ import annotations

import streamlit as st

from core.persona_manager import (
    create_persona,
    delete_persona,
    duplicate_persona,
    get_persona,
    list_personas,
    update_persona,
)

_ALL_INTENTS = ["analyze", "query", "filter", "aggregate", "transform", "export", "merge"]


def render_persona_panel() -> None:
    st.header("페르소나 관리")
    st.caption("AI의 역할과 말투를 설정합니다. 프리셋은 편집/복제만 가능하고, 커스텀은 자유롭게 관리할 수 있습니다.")

    personas = list_personas()

    # ── 새 페르소나 ──────────────────────────────────────────────────────────
    if st.button("+ 새 페르소나", type="primary"):
        st.session_state["pm_show_create"] = True

    if st.session_state.get("pm_show_create"):
        _render_create_form()
        st.divider()

    # ── 프리셋 ───────────────────────────────────────────────────────────────
    presets = {k: v for k, v in personas.items() if v["type"] == "preset"}
    if presets:
        st.subheader("프리셋")
        cols = st.columns(min(len(presets), 3))
        for i, (key, p) in enumerate(presets.items()):
            with cols[i % len(cols)]:
                _render_card(key, p, deletable=False)

    # ── 커스텀 ───────────────────────────────────────────────────────────────
    customs = {k: v for k, v in personas.items() if v["type"] == "custom"}
    if customs:
        st.subheader("커스텀")
        cols2 = st.columns(min(len(customs), 3))
        for i, (key, p) in enumerate(customs.items()):
            with cols2[i % len(cols2)]:
                _render_card(key, p, deletable=True)

    # ── Prompt 비교 ──────────────────────────────────────────────────────────
    st.divider()
    _render_prompt_compare(personas)


def _render_card(key: str, persona: dict, deletable: bool) -> None:
    with st.container(border=True):
        st.markdown(f"**{persona['name']}**")
        st.caption(persona["description"])
        intents = persona.get("intents", [])
        if intents:
            st.caption(f"자동 적용: {', '.join(intents)}")

        btn_cols = st.columns(2 if not deletable else 3)
        with btn_cols[0]:
            if st.button("편집", key=f"pm_edit_{key}", use_container_width=True):
                st.session_state[f"pm_editing_{key}"] = not st.session_state.get(f"pm_editing_{key}", False)
        with btn_cols[1]:
            if st.button("복제", key=f"pm_dup_{key}", use_container_width=True):
                st.session_state["pm_dup_source"] = key
        if deletable:
            with btn_cols[2]:
                if st.button("삭제", key=f"pm_del_{key}", use_container_width=True):
                    try:
                        delete_persona(key)
                        st.rerun()
                    except PermissionError as e:
                        st.error(str(e))

    if st.session_state.get(f"pm_editing_{key}"):
        _render_edit_form(key, persona)

    if st.session_state.get("pm_dup_source") == key:
        _render_dup_form(key)


def _render_create_form() -> None:
    with st.form("pm_create_form", border=True):
        st.markdown("**새 페르소나 만들기**")
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("이름", placeholder="예: 내 분석가")
        with c2:
            key = st.text_input("키 (영문, 공백 없이)", placeholder="예: my_analyst")
        description = st.text_input("한 줄 설명", placeholder="예: 예산 분석 전용 어시스턴트")
        about = st.text_area("About", placeholder="이 페르소나가 어떤 역할을 하는지 설명하세요.", height=80)
        response_style = st.text_area("말투 / 응답 스타일", placeholder="예: 간결하게, 코드 중심으로", height=80)
        system_prompt = st.text_area(
            "System Prompt (상세, 비워두면 위 내용으로 자동 생성)",
            height=180,
            placeholder="## 역할\n당신은...",
        )
        intents = st.multiselect("자동 적용 intent (선택)", _ALL_INTENTS)

        s, c = st.columns(2)
        with s:
            submitted = st.form_submit_button("저장", type="primary", use_container_width=True)
        with c:
            cancelled = st.form_submit_button("취소", use_container_width=True)

        if submitted:
            if not key or not name:
                st.error("이름과 키는 필수입니다.")
            else:
                sp = system_prompt.strip() or _auto_prompt(name, about, response_style)
                try:
                    create_persona(key=key, name=name, about=about,
                                   response_style=response_style, system_prompt=sp,
                                   description=description, intents=intents)
                    st.session_state["pm_show_create"] = False
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        if cancelled:
            st.session_state["pm_show_create"] = False
            st.rerun()


def _render_edit_form(key: str, persona: dict) -> None:
    with st.form(f"pm_edit_form_{key}", border=True):
        st.markdown(f"**{persona['name']} 편집**")
        name = st.text_input("이름", value=persona["name"])
        description = st.text_input("한 줄 설명", value=persona.get("description", ""))
        about = st.text_area("About", value=persona.get("about", ""), height=80)
        response_style = st.text_area("말투 / 응답 스타일", value=persona.get("response_style", ""), height=80)
        system_prompt = st.text_area("System Prompt", value=persona["system_prompt"], height=250)
        intents = st.multiselect("자동 적용 intent", _ALL_INTENTS, default=persona.get("intents", []))

        s, c = st.columns(2)
        with s:
            if st.form_submit_button("저장", type="primary", use_container_width=True):
                update_persona(key, name=name, description=description, about=about,
                               response_style=response_style, system_prompt=system_prompt,
                               intents=intents)
                st.session_state[f"pm_editing_{key}"] = False
                st.rerun()
        with c:
            if st.form_submit_button("취소", use_container_width=True):
                st.session_state[f"pm_editing_{key}"] = False
                st.rerun()


def _render_dup_form(source_key: str) -> None:
    with st.form(f"pm_dup_form_{source_key}", border=True):
        st.markdown("**복제**")
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input("새 이름")
        with c2:
            new_key = st.text_input("새 키 (영문)")
        s, c = st.columns(2)
        with s:
            if st.form_submit_button("복제", type="primary", use_container_width=True):
                if new_key and new_name:
                    try:
                        duplicate_persona(source_key, new_key, new_name)
                        st.session_state["pm_dup_source"] = None
                        st.rerun()
                    except (ValueError, KeyError) as e:
                        st.error(str(e))
        with c:
            if st.form_submit_button("취소", use_container_width=True):
                st.session_state["pm_dup_source"] = None
                st.rerun()


def _render_prompt_compare(personas: dict) -> None:
    st.subheader("System Prompt 비교")
    st.caption("두 페르소나의 System Prompt를 나란히 비교합니다.")

    keys = list(personas.keys())
    if len(keys) < 2:
        st.info("페르소나가 2개 이상이어야 비교할 수 있습니다.")
        return

    c1, c2 = st.columns(2)
    with c1:
        key_a = st.selectbox("페르소나 A", keys, format_func=lambda k: personas[k]["name"], key="cmp_a")
    with c2:
        default_b = keys[1] if keys[0] == key_a else keys[0]
        key_b = st.selectbox("페르소나 B", keys, index=keys.index(default_b),
                             format_func=lambda k: personas[k]["name"], key="cmp_b")

    pa = get_persona(key_a)
    pb = get_persona(key_b)
    if pa and pb:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"**{pa['name']}**")
            st.text_area("", value=pa["system_prompt"], height=400, disabled=True, key="cmp_txt_a")
        with col_b:
            st.markdown(f"**{pb['name']}**")
            st.text_area("", value=pb["system_prompt"], height=400, disabled=True, key="cmp_txt_b")


def _auto_prompt(name: str, about: str, response_style: str) -> str:
    parts = [f"## 역할\n{about}" if about else f"## 역할\n당신은 {name}입니다."]
    if response_style:
        parts.append(f"## 말투와 태도\n{response_style}")
    return "\n\n".join(parts)
