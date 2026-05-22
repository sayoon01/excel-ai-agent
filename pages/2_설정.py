"""설정 페이지 — 시스템 / 페르소나 / 모델 / 비교 테스트."""
from __future__ import annotations

import streamlit as st

from core.intent import INTENT_LABEL, detect_intent
from core.model_comparator import run_comparison
from core.persona_manager import get_persona, list_personas
from core.prompts.builder import augment_user_prompt, build_system_prompt
from core.system_monitor import (
    get_all_ollama_models, get_gpu_status, get_ollama_vram,
    get_system_status, load_ollama_model, unload_ollama_model,
)
from services.file_manager import collect_files_info, list_files
from ui.helpers import get_llm_client
from ui.persona_panel import render_persona_panel

st.header("설정")

tab_sys, tab_persona, tab_model, tab_compare = st.tabs([
    "🖥️ 시스템 모니터링",
    "🎭 페르소나 관리",
    "⚙️ 모델 관리",
    "🔬 비교 테스트",
])

# ── 탭 1: 시스템 모니터링 ────────────────────────────────────────────────────
with tab_sys:
    if st.button("🔄 새로고침", key="sys_refresh"):
        st.rerun()

    sys = get_system_status()
    gpus = get_gpu_status()
    ollama_host = st.session_state.get("ollama_host", "http://localhost:11434")
    vram_models = get_ollama_vram(ollama_host)

    # GPU 섹션
    if gpus:
        st.subheader("GPU")
        for g in gpus:
            with st.container(border=True):
                st.markdown(f"**GPU {g['index']} — {g['name']}**")
                c1, c2, c3 = st.columns(3)

                util = g["util_pct"]
                c1.metric("사용률", f"{util:.0f} %" if util is not None else "N/A")

                temp = g["temp_c"]
                c2.metric("온도", f"{temp:.0f} °C" if temp is not None else "N/A")

                power = g["power_w"]
                plimit = g["power_limit_w"]
                if power is not None:
                    pw_str = f"{power:.1f} W"
                    if plimit is not None:
                        pw_str += f" / {plimit:.0f} W"
                    c3.metric("전력", pw_str)
                else:
                    c3.metric("전력", "N/A")

                if util is not None:
                    st.progress(int(util) / 100)
    else:
        st.caption("GPU 정보를 가져올 수 없습니다.")

    # VRAM 점유 모델 섹션
    if vram_models:
        st.divider()
        st.subheader("VRAM 점유 모델 (Ollama)")
        total_vram = sum(m["vram_gb"] for m in vram_models)
        st.caption(f"총 {total_vram:.1f} GB — {len(vram_models)}개 모델 로드됨")

        for m in vram_models:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 2, 2, 1], vertical_alignment="center")
                c1.markdown(f"**{m['name']}**")
                c2.metric("VRAM", f"{m['vram_gb']:.1f} GB")
                c3.metric("규모", f"{m['param_size']} {m['quant']}")
                if c4.button("언로드", key=f"unload_{m['name']}", help=f"{m['name']} VRAM 해제"):
                    with st.spinner(f"{m['name']} 언로드 중..."):
                        ok = unload_ollama_model(m["name"], ollama_host)
                    if ok:
                        st.toast(f"{m['name']} 언로드 완료", icon="✅")
                    else:
                        st.toast(f"{m['name']} 언로드 실패", icon="❌")
                    st.rerun()

        _, col_all = st.columns([8, 2])
        if col_all.button("🗑️ 전체 언로드", type="secondary"):
            with st.spinner("전체 모델 언로드 중..."):
                results = [unload_ollama_model(m["name"], ollama_host) for m in vram_models]
            if all(results):
                st.toast("전체 언로드 완료", icon="✅")
            else:
                st.toast("일부 모델 언로드 실패", icon="⚠️")
            st.rerun()

    # 모델 로드 섹션
    st.divider()
    st.subheader("모델 로드")
    all_models = get_all_ollama_models(ollama_host)
    loaded_names = {m["name"] for m in vram_models}
    unloaded = [m for m in all_models if m not in loaded_names]

    if not all_models:
        st.caption("Ollama에서 모델 목록을 가져올 수 없습니다.")
    elif not unloaded:
        st.caption("설치된 모든 모델이 이미 VRAM에 로드되어 있습니다.")
    else:
        c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
        selected_model = c1.selectbox(
            "로드할 모델",
            options=unloaded,
            label_visibility="collapsed",
        )
        if c2.button("▶ 로드", type="primary"):
            with st.spinner(f"{selected_model} 로드 중... (모델 크기에 따라 수십 초 소요)"):
                ok = load_ollama_model(selected_model, ollama_host)
            if ok:
                st.toast(f"{selected_model} 로드 완료", icon="✅")
            else:
                st.toast(f"{selected_model} 로드 실패", icon="❌")
            st.rerun()

    st.divider()

    # CPU / RAM / 디스크
    st.subheader("시스템")
    col_cpu, col_ram, col_disk = st.columns(3)

    col_cpu.metric("CPU 사용률", f"{sys['cpu_pct']:.1f} %")
    col_cpu.progress(sys["cpu_pct"] / 100)

    col_ram.metric(
        "RAM",
        f"{sys['ram_used_gb']:.1f} / {sys['ram_total_gb']:.1f} GB",
        f"{sys['ram_pct']:.0f} %",
    )
    col_ram.progress(sys["ram_pct"] / 100)

    col_disk.metric(
        "디스크 (/)",
        f"{sys['disk_used_gb']:.1f} / {sys['disk_total_gb']:.1f} GB",
        f"{sys['disk_pct']:.0f} %",
    )
    col_disk.progress(sys["disk_pct"] / 100)

# ── 탭 2: 페르소나 관리 ──────────────────────────────────────────────────────
with tab_persona:
    render_persona_panel()

# ── 탭 3: 모델 관리 ─────────────────────────────────────────────────────────
with tab_model:
    # 현재 모델 상태 요약
    st.subheader("현재 모델")
    provider = st.session_state.provider
    with st.container(border=True):
        if provider == "Ollama":
            chat_m = st.session_state.get("ollama_model") or "미선택"
            code_m = st.session_state.get("ollama_code_model") or "(대화 모델과 동일)"
            c1, c2, c3 = st.columns(3)
            c1.metric("프로바이더", "Ollama")
            c2.metric("대화 모델", chat_m)
            c3.metric("코드 모델", code_m)
            st.caption(f"Host: {st.session_state.ollama_host}")
        elif provider == "Gemini":
            c1, c2 = st.columns(2)
            c1.metric("프로바이더", "Gemini")
            c2.metric("모델", st.session_state.get("gemini_model", "-"))
        elif provider == "OpenAI":
            c1, c2 = st.columns(2)
            c1.metric("프로바이더", "OpenAI")
            c2.metric("모델", st.session_state.get("openai_model", "-"))
    st.caption("프로바이더·모델 변경은 사이드바에서 합니다.")

    st.divider()

    # Ollama 호스트 설정
    if provider == "Ollama":
        st.subheader("Ollama 연결")
        st.text_input(
            "Ollama Host",
            value=st.session_state.ollama_host,
            key="ollama_host",
            help="Ollama 서버 주소 (기본값: http://localhost:11434)",
        )
        st.divider()

    # 생성 파라미터
    st.subheader("생성 파라미터")
    st.slider(
        "Temperature",
        min_value=0.0, max_value=2.0, step=0.05,
        key="llm_temperature",
        help="낮을수록 일관된 답변, 높을수록 창의적 답변. 코드 생성은 0.2~0.5 권장.",
    )
    st.slider(
        "Max Tokens",
        min_value=512, max_value=16384, step=512,
        key="llm_max_tokens",
        help="응답 최대 토큰 수.",
    )

    st.divider()

    # 프롬프트 디버그
    st.subheader("프롬프트 디버그")
    st.caption("실제로 LLM에 전송되는 시스템 프롬프트와 사용자 프롬프트를 확인합니다.")

    debug_input = st.text_area(
        "테스트할 입력",
        placeholder="예: 매출 기준으로 필터해줘",
        height=80,
        key="debug_input",
    )

    if debug_input:
        _fi = collect_files_info(list_files())
        _intent = detect_intent(debug_input)

        st.caption(f"감지된 의도: **{INTENT_LABEL.get(_intent, _intent)}**")

        col_user, col_sys = st.columns(2)
        with col_user:
            st.markdown("**사용자 프롬프트 (보강 후)**")
            st.code(augment_user_prompt(debug_input, _fi), language="text")
        with col_sys:
            st.markdown("**시스템 프롬프트**")
            st.code(build_system_prompt(_fi, _intent), language="text")

# ── 탭 4: 비교 테스트 ───────────────────────────────────────────────────────
with tab_compare:
    st.caption("같은 프롬프트를 여러 페르소나로 실행해 응답과 속도를 비교합니다.")

    _all_personas = list_personas()
    _persona_names = [p["name"] for p in _all_personas.values()]
    _name_to_key = {p["name"]: k for k, p in _all_personas.items()}

    if len(_persona_names) < 2:
        st.warning("비교하려면 페르소나가 2개 이상 필요합니다. 페르소나 관리 탭에서 추가하세요.")
    else:
        _sel_names = st.multiselect(
            "비교할 페르소나 선택 (2~3개)",
            options=_persona_names,
            default=_persona_names[:2],
            max_selections=3,
            key="compare_persona_sel",
        )

        _compare_prompt = st.text_area(
            "테스트 프롬프트",
            placeholder="예: 이 데이터에서 가장 중요한 인사이트를 알려줘",
            height=80,
            key="compare_prompt",
        )

        _run_btn = st.button(
            "▶ 비교 실행",
            disabled=(len(_sel_names) < 2 or not _compare_prompt.strip()),
            type="primary",
        )

        if _run_btn and _compare_prompt.strip() and len(_sel_names) >= 2:
            _client, _err = get_llm_client()
            if _err:
                st.error(_err)
            else:
                _fi = collect_files_info(list_files())
                _configs = []
                for name in _sel_names:
                    key = _name_to_key[name]
                    system = build_system_prompt(_fi, persona_key=key)
                    _configs.append({"label": name, "system": system, "client": _client})

                with st.spinner(f"{len(_sel_names)}개 페르소나 실행 중..."):
                    _results = run_comparison(_compare_prompt, _configs)

                st.session_state["compare_results"] = _results

        # 결과 표시
        if st.session_state.get("compare_results"):
            st.divider()
            _res = st.session_state["compare_results"]
            cols = st.columns(len(_res))
            for col, r in zip(cols, _res):
                with col:
                    if r["error"]:
                        st.error(f"**{r['label']}** — 오류")
                        st.caption(r["error"])
                    else:
                        st.markdown(f"**{r['label']}**")
                        st.caption(f"응답 시간: {r['latency_s']:.1f}초")
                        st.markdown(r["response"])
