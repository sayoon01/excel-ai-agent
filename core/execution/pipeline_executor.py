"""파이프라인 사전 처리 — LLM 호출 전까지의 Step 1~3."""
from __future__ import annotations

import re

from core.routing.intent import detect_intent
from core.persona_manager import get_persona, resolve_persona_key
from core.execution.pipeline import PipelineStage, PipelineState, ToolExecution
from core.prompts.builder import augment_user_prompt, build_system_prompt
from core.routing.task_router import classify_task

# tiktoken 인코딩 캐시 — 모델별로 한 번만 로드
_ENCODER_CACHE: dict[str, object] = {}

# OpenAI 모델명 → tiktoken 인코딩 이름
_OPENAI_ENCODINGS = {
    "gpt-4o":        "o200k_base",
    "gpt-4o-mini":   "o200k_base",
    "gpt-4-turbo":   "cl100k_base",
    "gpt-4":         "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
}


def _get_encoder(model_name: str = ""):
    import tiktoken
    enc_name = _OPENAI_ENCODINGS.get(model_name, "cl100k_base")
    if enc_name not in _ENCODER_CACHE:
        _ENCODER_CACHE[enc_name] = tiktoken.get_encoding(enc_name)
    return _ENCODER_CACHE[enc_name]


def estimate_tokens(text: str, model_name: str = "") -> int:
    """tiktoken으로 토큰 수 계산.
    OpenAI 모델은 해당 인코딩, 그 외(Gemini·Ollama)는 cl100k_base로 근사.
    """
    try:
        enc = _get_encoder(model_name)
        return len(enc.encode(text))
    except Exception:
        # tiktoken 로드 실패 시 글자 수 기반 폴백
        return len(text) // 3


def run_pre_generation(
    user_prompt: str,
    files_info: list[dict],
    last_result_info: dict | None = None,
    persona_override: str | None = None,
    compact: bool = False,
    recent_messages: list | None = None,
    llm_client=None,
) -> PipelineState:
    """LLM 호출 전 Step 1~3 실행. 기존 함수를 그대로 호출하면서 메트릭만 수집."""
    state = PipelineState(user_prompt=user_prompt)

    # Step 1: Intent 분류 + Task 분류 (mode + confidence + options)
    # llm_client가 있으면 confidence < 0.8 케이스를 LLM이 직접 분류
    m1 = state.start_stage(PipelineStage.INTENT)
    state.intent = detect_intent(user_prompt)
    state.task_config = classify_task(user_prompt, state.intent, client=llm_client)
    state.mode = state.task_config["mode"]
    m1.details = {
        "intent":     state.intent,
        "mode":       state.mode,
        "tool":       state.task_config.get("tool"),
        "confidence": state.task_config.get("confidence", 0.0),
    }
    m1.finish()

    # Step 2: Persona 결정
    m2 = state.start_stage(PipelineStage.PERSONA)
    state.persona_key = persona_override or resolve_persona_key(state.intent)
    persona = get_persona(state.persona_key)
    state.persona_name = persona["name"] if persona else "기본"
    m2.details = {"key": state.persona_key, "name": state.persona_name}
    m2.finish()

    # Step 3: Prompt 보강
    m3 = state.start_stage(PipelineStage.PROMPT_ENHANCE)
    state.augmented_prompt = augment_user_prompt(
        user_prompt, files_info, last_result_info
    )
    m3.details = {
        "original_len": len(user_prompt),
        "augmented_len": len(state.augmented_prompt),
        "was_enhanced": state.augmented_prompt != user_prompt,
    }
    m3.finish()

    # System prompt 빌드 (메트릭 포함)
    state.system_prompt = build_system_prompt(
        files_info,
        state.intent,
        compact=compact,
        last_result_info=last_result_info,
        recent_messages=recent_messages,
        persona_key=state.persona_key,
        mode=state.mode,
    )
    state.system_prompt_token_est = estimate_tokens(state.system_prompt, state.model_name)

    return state


def record_pipeline_run(
    state: PipelineState,
    turn: int,
    success: bool,
    result_rows: int | None = None,
    chained: bool = False,
) -> ToolExecution:
    """PipelineState에서 ToolExecution 레코드를 생성해 반환."""
    return ToolExecution(
        turn=turn,
        mode=state.mode,
        tool_name=state.task_config.get("tool", ""),
        user_prompt=state.user_prompt[:60],
        success=success,
        duration_ms=state.get_total_duration_ms(),
        result_rows=result_rows,
        chained=chained,
    )


def parse_llm_response(state: PipelineState, response: str) -> PipelineState:
    """LLM 응답에서 코드 블록과 설명 텍스트 분리."""
    state.response_token_est = estimate_tokens(response, state.model_name)

    code_blocks = re.findall(r"```python\s*\n(.*?)```", response, re.DOTALL)
    if code_blocks:
        state.has_code = True
        state.generated_code = code_blocks[0]

        code_start = response.find("```python")
        if code_start > 0:
            state.code_explanation = response[:code_start].strip()
    else:
        state.has_code = False

    return state
