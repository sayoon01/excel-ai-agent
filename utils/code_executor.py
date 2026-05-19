"""Safe sandboxed Python/pandas code execution for LLM-generated code."""
from __future__ import annotations

import ast
import io
import signal
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from utils.file_manager import RESULT_DIR, list_files, read_file

BLOCKED_MODULES = frozenset({
    "os", "subprocess", "sys", "shutil", "importlib",
    "socket", "http", "urllib", "requests", "httpx",
    "pathlib", "glob", "pickle", "shelve", "marshal",
    "ctypes", "multiprocessing", "threading",
    "signal", "atexit", "code", "codeop", "compileall",
})

BLOCKED_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__",
    "open", "input", "breakpoint",
    "globals", "locals", "vars",
    "getattr", "setattr", "delattr",
    "memoryview",
})


@dataclass
class ExecutionResult:
    success: bool
    output: str = ""
    error: str = ""
    result_df: pd.DataFrame | None = None
    saved_files: list[str] = field(default_factory=list)


def _validate_code(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"문법 오류: {e}"]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                if name in BLOCKED_MODULES:
                    violations.append(f"허용되지 않는 import: {name}")
                elif name not in {"pandas", "numpy", "pd", "np"}:
                    violations.append(
                        f"import 불필요: {name} (pd, np는 이미 사용 가능)"
                    )
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
                violations.append(f"차단된 내장 함수: {node.func.id}")
    return violations


def _make_safe_builtins() -> dict:
    import builtins
    safe = {}
    for name in dir(builtins):
        if name not in BLOCKED_BUILTINS and not name.startswith("_"):
            safe[name] = getattr(builtins, name)
    safe["__build_class__"] = builtins.__build_class__
    safe["__name__"] = "__main__"
    return safe


def _make_save_fn(saved_files: list[str], namespace: dict):
    def save(filename: str, df: pd.DataFrame | None = None):
        if df is None:
            df = namespace.get("result")
        if df is None:
            raise ValueError("저장할 DataFrame이 없습니다. result에 할당하거나 df 인자를 전달하세요.")
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"DataFrame이 필요합니다. {type(df).__name__} 전달됨.")
        name = Path(filename).name
        if "/" in filename or "\\" in filename or ".." in filename:
            raise ValueError("유효하지 않은 파일명입니다.")
        suffix = Path(name).suffix.lower()
        if suffix not in (".xlsx", ".csv"):
            raise ValueError(f"지원하지 않는 형식: {suffix}. .xlsx 또는 .csv를 사용하세요.")
        dest = RESULT_DIR / name
        if suffix == ".csv":
            df.to_csv(dest, index=False)
        else:
            df.to_excel(dest, index=False)
        saved_files.append(name)
    return save


class _Timeout:
    def __init__(self, seconds: int):
        self.seconds = seconds
        self._old = None

    def __enter__(self):
        try:
            self._old = signal.signal(signal.SIGALRM, self._handler)
            signal.alarm(self.seconds)
        except (ValueError, OSError):
            pass
        return self

    def __exit__(self, *_):
        try:
            signal.alarm(0)
            if self._old is not None:
                signal.signal(signal.SIGALRM, self._old)
        except (ValueError, OSError):
            pass

    @staticmethod
    def _handler(signum, frame):
        raise TimeoutError("코드 실행 시간이 초과되었습니다.")


def execute(
    code: str,
    timeout_seconds: int = 30,
    last_result: pd.DataFrame | None = None,
) -> ExecutionResult:
    violations = _validate_code(code)
    if violations:
        return ExecutionResult(
            success=False,
            error="코드 검증 실패:\n" + "\n".join(f"  - {v}" for v in violations),
        )

    saved_files: list[str] = []
    files = {fname: read_file(fname) for fname in list_files()}
    files = {k: v for k, v in files.items() if v is not None}

    namespace: dict = {
        "files": files,
        "last_result": last_result,   # 직전 작업 결과 DataFrame
        "pd": pd,
        "np": np,
        "result": None,
        "__builtins__": _make_safe_builtins(),
    }
    namespace["save"] = _make_save_fn(saved_files, namespace)

    stdout_capture = io.StringIO()
    namespace["print"] = lambda *args, **kwargs: print(
        *args, **kwargs, file=stdout_capture
    )

    try:
        with _Timeout(timeout_seconds):
            exec(compile(code, "<llm_generated>", "exec"), namespace)  # noqa: S102
    except TimeoutError as e:
        return ExecutionResult(
            success=False,
            output=stdout_capture.getvalue(),
            error=str(e),
        )
    except Exception:
        return ExecutionResult(
            success=False,
            output=stdout_capture.getvalue(),
            error=traceback.format_exc(),
        )

    result_df = namespace.get("result")
    if result_df is not None and not isinstance(result_df, pd.DataFrame):
        result_df = None

    return ExecutionResult(
        success=True,
        output=stdout_capture.getvalue(),
        result_df=result_df,
        saved_files=saved_files,
    )
