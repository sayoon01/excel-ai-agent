"""파일 관리 페이지 — 업로드, 미리보기, 품질 리포트, 결과 파일."""
from __future__ import annotations

import pandas as pd
import streamlit as st

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
from ui.quality_report import load_files_info, render_quality_report


@st.dialog("전체 보기", width="large")
def _fullscreen_dialog(fname: str, sheet_name: str | None = None) -> None:
    df = read_file(fname, sheet_name=sheet_name)
    if df is None:
        st.error("파일을 읽을 수 없습니다.")
        return
    for col in df.columns:
        if pd.api.types.is_extension_array_dtype(df[col]):
            df[col] = df[col].astype(object)
    st.caption(f"📄 {fname}  ·  {len(df):,}행 × {len(df.columns)}열")
    st.dataframe(df, use_container_width=True, height=620)

st.header("파일 관리")


@st.cache_data(show_spinner=False)
def _cached_file_info(name: str) -> dict | None:
    return get_file_info(name)


def _clear_caches() -> None:
    load_files_info.clear()
    _cached_file_info.clear()


# ── 업로드 ────────────────────────────────────────────────────────────────────

st.subheader("파일 업로드")
uploaded = st.file_uploader(
    "엑셀 / CSV 파일을 업로드하세요",
    type=["xlsx", "xls", "csv"],
    accept_multiple_files=True,
)

if uploaded:
    existing = set(list_files())
    duplicates = [f.name for f in uploaded if f.name in existing]

    if duplicates:
        st.warning(f"이미 존재하는 파일: {', '.join(duplicates)}")
        col_ow, col_skip = st.columns(2)
        with col_ow:
            if st.button("덮어쓰기", key="btn_overwrite_dup"):
                for f in uploaded:
                    save_uploaded(f)
                _clear_caches()
                st.success(f"{len(uploaded)}개 파일 저장 완료")
                st.rerun()
        with col_skip:
            new_files = [f for f in uploaded if f.name not in existing]
            btn_label = f"새 파일만 저장 ({len(new_files)}개)" if new_files else "새 파일 없음"
            if st.button(btn_label, key="btn_new_only", disabled=not new_files):
                for f in new_files:
                    save_uploaded(f)
                _clear_caches()
                st.success(f"{len(new_files)}개 새 파일 업로드 완료")
                st.rerun()
    else:
        for f in uploaded:
            save_uploaded(f)
        _clear_caches()
        st.success(f"{len(uploaded)}개 파일 업로드 완료")
        st.rerun()

# ── 업로드된 파일 목록 ────────────────────────────────────────────────────────

files = list_files()

if not files:
    st.info("업로드된 파일이 없습니다.")
else:
    st.subheader(f"업로드된 파일 ({len(files)}개)")
    for fname in files:
        info = _cached_file_info(fname)
        col_name, col_del = st.columns([9, 1])
        with col_name:
            if info:
                sheet_count = info.get("sheet_count", 0)
                sheet_warn = f"  ⚠ {sheet_count} sheets" if sheet_count > 1 else ""
                st.markdown(f"**📄 {fname}**{sheet_warn}")
                detail = f"{info['rows']:,}행 × {info['columns']}열  |  {info['size_kb']} KB"
                if info.get("used_range"):
                    detail += f"  |  {info['used_range']}"
                st.caption(detail)
                if sheet_count > 1:
                    names = ", ".join(info.get("sheet_names", [])[:3])
                    st.caption(f"시트: {names}{'...' if sheet_count > 3 else ''}")
            else:
                st.markdown(f"**📄 {fname}**")
        with col_del:
            if st.button("✕", key=f"del_{fname}", help="파일 삭제"):
                delete_file(fname)
                _clear_caches()
                st.rerun()

    # ── 미리보기 + 품질 리포트 ─────────────────────────────────────────────

    st.divider()
    st.subheader("미리보기 및 품질 리포트")

    preview_target = st.selectbox("파일 선택", ["선택하세요..."] + files)
    if preview_target and preview_target != "선택하세요...":
        target_info = _cached_file_info(preview_target)
        sheet_names = target_info.get("sheet_names", []) if target_info else []

        selected_sheet: str | None = None
        if len(sheet_names) > 1:
            selected_sheet = st.selectbox(
                "시트 선택",
                sheet_names,
                key=f"sheet_sel_{preview_target}",
            )
            st.session_state.selected_sheets[preview_target] = selected_sheet
        elif preview_target in st.session_state.selected_sheets:
            del st.session_state.selected_sheets[preview_target]

        df_preview = preview_file(preview_target, sheet_name=selected_sheet)
        if df_preview is not None:
            st.dataframe(df_preview, use_container_width=True, height=220)
            if st.button("⛶ 전체 보기", key="btn_fullscreen_preview"):
                _fullscreen_dialog(preview_target, selected_sheet)

        all_info = load_files_info(tuple(files))
        selected_info = [fi for fi in all_info if fi["name"] == preview_target]
        if selected_info:
            render_quality_report(selected_info)

# ── 결과 파일 ─────────────────────────────────────────────────────────────────

result_files = list_results()
if result_files:
    st.divider()
    st.subheader(f"결과 파일 ({len(result_files)}개)")
    for fname in result_files:
        col_n, col_dl, col_del = st.columns([6, 1, 1])
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
            if st.button("✕", key=f"del_res_{fname}", help="삭제"):
                delete_result(fname)
                st.rerun()
