"""페르소나 / 모델 비교 테스트 — 같은 프롬프트를 여러 설정으로 실행."""
from __future__ import annotations

import time

from core.llm_client import LLMClient


def run_comparison(
    prompt: str,
    configs: list[dict],  # [{"label": str, "system": str, "client": LLMClient}]
) -> list[dict]:
    """각 config에 대해 동일 프롬프트를 순차 실행하고 결과를 반환.

    Returns:
        [{"label": str, "response": str, "latency_s": float, "error": str | None}]
    """
    messages = [{"role": "user", "content": prompt}]
    results = []
    for cfg in configs:
        t0 = time.time()
        try:
            response = "".join(cfg["client"].chat_stream(messages, cfg["system"]))
            results.append({
                "label": cfg["label"],
                "response": response,
                "latency_s": time.time() - t0,
                "error": None,
            })
        except Exception as e:
            results.append({
                "label": cfg["label"],
                "response": "",
                "latency_s": time.time() - t0,
                "error": str(e),
            })
    return results
