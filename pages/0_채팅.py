"""AI 채팅 페이지."""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from services.file_manager import list_files, RESULT_DIR
from core.persona_manager import list_personas
from core.execution.pipeline import PipelineStage
from core.execution.pipeline_executor import parse_llm_response, record_pipeline_run, run_pre_generation
from core.chat_history import new_chat_id, save_chat
from core.execution.code_executor import ExecutionResult
from core.tools.dispatcher import dispatch_tool
from ui.chat_layout import apply_chat_layout_styles, chat_input_spacer
from ui.chat_view import render_chat_history, render_last_result_banner
from ui.helpers import get_embedder, get_llm_client
from ui.quality_report import load_files_info

if not st.session_state.current_chat_id:
    st.session_state.current_chat_id = new_chat_id()


def _run_dsl_router(user_prompt: str, files_info: list[dict],
                    last_result_info: dict | None) -> dict | None:
    """DSL 라우터(LLM) + 인터프리터 실행. 결과 dict 반환 (JSON 직렬화 가능).

    실패해도 None을 반환해 기존 흐름을 깨뜨리지 않는다.
    """
    try:
        from core.routing.llm_router import route
        from core.dsl import run_pipeline
    except Exception:
        return None

    client, err = get_llm_client(intent="query")
    if err or client is None:
        return None

    t0 = time.time()
    try:
        r = route(user_prompt, files_info, client, last_result_info=last_result_info)
    except Exception as exc:
        return {"intent": "error", "error": f"라우터 예외: {exc}",
                "rt_ms": int((time.time() - t0) * 1000)}
    rt_ms = int((time.time() - t0) * 1000)

    result: dict = {
        "intent":      r.intent,
        "explanation": r.explanation,
        "message":     r.message,
        "suggested":   r.suggested,
        "pipeline":    r.pipeline,
        "error":       r.error,
        "suggestion":  r.suggestion,
        "rt_ms":       rt_ms,
        "exec_ok":     None,
        "exec_type":   None,
        "exec_summary": None,
        "exec_preview": None,    # dataframe head dict
        "exec_path":   None,     # plot 경로
        "exec_err":    None,
        "exec_ms":     None,
        "log":         None,
    }

    if not r.ok() or r.intent != "dsl" or not r.pipeline:
        return result

    t1 = time.time()
    try:
        res = run_pipeline(r.pipeline, files_info=files_info)
    except Exception as exc:
        result["exec_ok"]  = False
        result["exec_err"] = f"인터프리터 예외: {exc}"
        result["exec_ms"]  = int((time.time() - t1) * 1000)
        return result
    result["exec_ms"]      = int((time.time() - t1) * 1000)
    result["exec_type"]    = res.get("type")
    result["exec_summary"] = res.get("summary")
    result["log"]          = res.get("log")
    if res.get("type") == "error":
        result["exec_ok"]  = False
        result["exec_err"] = res.get("message")
        return result
    result["exec_ok"] = True
    v = res.get("value")
    if isinstance(v, pd.DataFrame):
        head = v.head(50)
        result["exec_preview"] = {
            "columns": [str(c) for c in head.columns],
            "rows":    head.astype(object).where(head.notna(), None).values.tolist(),
            "shape":   [int(v.shape[0]), int(v.shape[1])],
        }
    elif res.get("type") == "plot":
        result["exec_path"] = str(v) if v else None
    return result

_SUGGESTION_SYSTEM = (
    "너는 데이터 분석 어시스턴트야. "
    "방금 나눈 대화를 보고 사용자가 자연스럽게 이어서 할 만한 후속 작업을 정확히 3개 제안해. "
    "조건:\n"
    "- 한국어, 각 항목은 한 줄, 반드시 15자 이내 (버튼에 표시되므로 짧게)\n"
    "- 번호/기호/이모지 없이 줄바꿈으로만 구분\n"
    "- '~해줘' 형태의 짧은 명령형으로 작성 (예: '결측치 제거해줘', 'Unnamed 열 삭제해줘')\n"
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


apply_chat_layout_styles()

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
chat_input_spacer()

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
    # confidence < 0.8인 애매한 케이스를 LLM이 직접 분류하도록 client 전달
    _pre_client, _pre_err = get_llm_client(intent="query")
    _classify_client = None if _pre_err else _pre_client
    _embedder = get_embedder()
    state = run_pre_generation(
        user_prompt=prompt,
        files_info=files_info,
        last_result_info=last_result_info,
        persona_override=st.session_state.get("selected_persona_key"),
        compact=is_compact,
        recent_messages=st.session_state.messages,
        llm_client=_classify_client,
        embedder=_embedder,
    )
    st.session_state.last_intent = state.intent

    st.session_state.messages.append({
        "role": "user",
        "content": state.user_prompt,
        "display": prompt,
        "intent": state.intent,
    })
    with st.chat_message("user"):
        st.markdown(prompt)

    # ── Tool 모드: LLM 없이 직접 실행 ──────────────────────────────────────────
    tool_name = state.task_config.get("tool") or (
        "create_chart" if state.task_config.get("needs_chart") else None
    )
    if state.mode == "tool" and tool_name:
        _tool_label = {
            "get_row_count": "행 수 조회", "analyze_missing": "결측치 분석",
            "get_profile": "컬럼 프로파일", "aggregate_data": "집계",
            "select_columns": "컬럼 추출",
            "filter_rows": "필터", "sort_rows": "정렬",
            "merge_files": "파일 병합", "merge_same_format": "동일 양식 통합",
            "create_chart": "차트 생성",
        }.get(tool_name, tool_name)

        with st.spinner(f"🔧 {_tool_label} 실행 중..."):
            m_tool = state.start_stage(PipelineStage.EXECUTING)
            m_tool.details = {
                "tool":       tool_name,
                "tool_label": _tool_label,
                "files":      [f.get("name", "") for f in files_info],
                "confidence": state.task_config.get("confidence", 0.0),
            }
            _extra = {"llm_client": _classify_client}   # 컬럼명 LLM 추론용
            # export_data는 항상, 나머지는 use_last_result 플래그가 있을 때만 전달
            if tool_name == "export_data" or state.task_config.get("use_last_result"):
                _extra["last_result"] = st.session_state.get("last_result")
            tool_result = dispatch_tool(tool_name, files_info, prompt=prompt, **_extra)
            m_tool.details["result_type"]  = tool_result.get("type", "")
            m_tool.details["result_label"] = tool_result.get("label", "")
            m_tool.details["cached"]       = tool_result.get("cached", False)
            m_tool.finish()

        if tool_result.get("type") == "error":
            answer = f"도구 실행 오류: {tool_result.get('message', '알 수 없는 오류')}"
            exec_res = ExecutionResult(success=False, error=answer)
        else:
            summary = tool_result.get("summary", "")
            label   = tool_result.get("label", "결과")
            answer  = f"**{label}**\n\n{summary}" if summary else f"**{label}**"
            rtype   = tool_result.get("type", "string")
            rval    = tool_result.get("value")
            rdf     = rval if rtype == "dataframe" and isinstance(rval, pd.DataFrame) else None

            from pathlib import Path as _Path
            from services.result_naming import result_filename, saved_files_hint

            saved: list[str] = list(tool_result.get("saved_files") or [])
            needs_export = state.task_config.get("needs_export", False)
            needs_chart = state.task_config.get("needs_chart", False)

            # 저장 요청(needs_export)일 때만 xlsx 저장 — export_data는 이미 saved에 포함
            if rdf is not None and not saved and needs_export:
                fname = result_filename(prompt=prompt, label=label, intent=state.intent)
                dest = RESULT_DIR / fname
                rdf.to_excel(dest, index=False)
                saved.append(fname)

            # 차트 전용 도구 또는 plot 결과
            if rtype == "plot" and rval:
                chart_name = _Path(str(rval)).name
                if chart_name not in saved:
                    saved.append(chart_name)

            # 필터·집계 등 + 차트 동시 요청
            if needs_chart and rdf is not None:
                from core.tools.chart_tools import create_chart as _create_chart_fn
                _chart_res = _create_chart_fn(files_info=files_info, prompt=prompt)
                if _chart_res.get("type") == "plot":
                    _cp = _Path(str(_chart_res["value"]))
                    if _cp.exists() and _cp.name not in saved:
                        saved.append(_cp.name)

            if saved:
                answer += saved_files_hint(saved)

            exec_res = ExecutionResult(
                success=True,
                result_df=rdf,
                result_type=rtype,
                result_value=rval if rdf is None else None,
                saved_files=saved,
            )

        # needs_summary: tool 결과를 LLM이 자연어로 해석
        needs_summary = state.task_config.get("needs_summary", False)
        if needs_summary and exec_res.success and exec_res.result_df is not None:
            _sum_client, _sum_err = get_llm_client(intent=state.intent)
            if not _sum_err:
                _df_preview = exec_res.result_df.head(10).to_markdown(index=False)
                _sum_msgs = [{"role": "user", "content": (
                    f"다음은 '{prompt}' 요청에 대한 분석 결과입니다:\n\n"
                    f"{_df_preview}\n\n"
                    "이 결과를 2~3문장으로 핵심만 한국어로 요약해줘."
                )}]
                try:
                    with st.spinner("요약 생성 중..."):
                        _summary_text = "".join(_sum_client.chat_stream(_sum_msgs, ""))
                    if _summary_text.strip():
                        answer = f"{answer}\n\n**요약**: {_summary_text.strip()}"
                except Exception:
                    pass

        # ── DSL 라우터 (shadow 실행) — 사용자에게 비교용으로 함께 표시 ──
        with st.spinner("🧪 DSL 라우터 비교 중..."):
            _dsl_res = _run_dsl_router(prompt, files_info, last_result_info)

        msg_idx = len(st.session_state.messages)
        state = parse_llm_response(state, answer)
        _msg: dict = {"role": "assistant", "content": answer,
                      "pipeline": state.to_dict()}
        if _dsl_res:
            _msg["dsl_result"] = _dsl_res
            st.session_state.dsl_results[msg_idx] = _dsl_res
        st.session_state.messages.append(_msg)
        st.session_state.pipeline_states[msg_idx] = state
        st.session_state.exec_results[msg_idx] = exec_res
        if exec_res.success and exec_res.result_df is not None:
            st.session_state.last_result = exec_res.result_df
            st.session_state.result_history.append(exec_res.result_df)
        # 세션 히스토리 기록
        _rows = len(exec_res.result_df) if exec_res.result_df is not None else None
        _chained = state.task_config.get("use_last_result", False)
        st.session_state.session_history.record(
            record_pipeline_run(state, msg_idx, exec_res.success, _rows, _chained)
        )
        save_chat(st.session_state.current_chat_id, st.session_state.messages)
        st.rerun()

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

        # ── DSL 라우터 (shadow 실행) ──
        with st.spinner("🧪 DSL 라우터 비교 중..."):
            _dsl_res = _run_dsl_router(prompt, files_info, last_result_info)

        msg_idx = len(st.session_state.messages)
        _msg: dict = {"role": "assistant", "content": response,
                      "pipeline": state.to_dict()}
        if _dsl_res:
            _msg["dsl_result"] = _dsl_res
            st.session_state.dsl_results[msg_idx] = _dsl_res
        st.session_state.messages.append(_msg)
        st.session_state.pipeline_states[msg_idx] = state
        # 세션 히스토리 기록
        st.session_state.session_history.record(
            record_pipeline_run(state, msg_idx, True)
        )
        save_chat(st.session_state.current_chat_id, st.session_state.messages)

        with st.spinner("후속 질문 생성 중..."):
            suggs = _generate_suggestions(client, prompt, response)
        if suggs:
            st.session_state.suggestions[msg_idx] = suggs

        st.rerun()
