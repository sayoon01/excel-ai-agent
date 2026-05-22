"""파이프라인 사전 처리 — LLM 호출 전까지의 Step 1~3."""
from __future__ import annotations

import re

from core.intent import detect_intent
from core.persona_manager import get_persona, resolve_persona_key
from core.pipeline import PipelineStage, PipelineState
from core.prompts.builder import augment_user_prompt, build_system_prompt


def estimate_tokens(text: str) -> int:
    """토큰 수 추정 (한국어: 글자 × 0.5, 영문 단어 × 1.3)."""
    korean = sum(1 for c in text if "가" <= c <= "힣")
    words = len(text.split())
    return int(korean * 0.5 + words * 1.3)


def run_pre_generation(
    user_prompt: str,
    files_info: list[dict],
    last_result_info: dict | None = None,
    persona_override: str | None = None,
    compact: bool = False,
    recent_messages: list | None = None,
) -> PipelineState:
    """LLM 호출 전 Step 1~3 실행. 기존 함수를 그대로 호출하면서 메트릭만 수집."""
    state = PipelineState(user_prompt=user_prompt)

    # Step 1: Intent 분류
    m1 = state.start_stage(PipelineStage.INTENT)
    state.intent = detect_intent(user_prompt)
    m1.details = {"intent": state.intent}
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
    )
    state.system_prompt_token_est = estimate_tokens(state.system_prompt)

    return state


def parse_llm_response(state: PipelineState, response: str) -> PipelineState:
    """LLM 응답에서 코드 블록과 설명 텍스트 분리."""
    state.response_token_est = estimate_tokens(response)

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
