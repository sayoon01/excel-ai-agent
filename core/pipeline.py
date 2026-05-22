"""채팅 실행 파이프라인 상태 관리."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PipelineStage(str, Enum):
    INTENT          = "intent"
    PERSONA         = "persona"
    PROMPT_ENHANCE  = "prompt_enhance"
    LLM_THINKING    = "llm_thinking"
    CODE_GENERATED  = "code_generated"
    EXECUTING       = "executing"
    COMPLETED       = "completed"
    ERROR           = "error"


@dataclass
class StageMetrics:
    stage: PipelineStage
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    duration_ms: int = 0
    details: dict = field(default_factory=dict)

    def finish(self) -> None:
        self.ended_at = datetime.now()
        self.duration_ms = int(
            (self.ended_at - self.started_at).total_seconds() * 1000
        )


@dataclass
class PipelineState:
    # 입력
    user_prompt: str = ""
    augmented_prompt: str = ""

    # 분류
    intent: str = ""
    persona_key: str = ""
    persona_name: str = ""

    # 프롬프트
    system_prompt: str = ""
    system_prompt_token_est: int = 0

    # LLM 응답
    model_name: str = ""
    provider: str = ""
    response_token_est: int = 0

    # 코드
    generated_code: str = ""
    code_explanation: str = ""
    has_code: bool = False

    # 메트릭
    current_stage: PipelineStage = PipelineStage.INTENT
    stages: list[StageMetrics] = field(default_factory=list)

    def start_stage(self, stage: PipelineStage, **details) -> StageMetrics:
        self.current_stage = stage
        m = StageMetrics(stage=stage, details=details)
        self.stages.append(m)
        return m

    def get_total_duration_ms(self) -> int:
        return sum(s.duration_ms for s in self.stages)

    def get_stage_duration_ms(self, stage: PipelineStage) -> int:
        for s in self.stages:
            if s.stage == stage:
                return s.duration_ms
        return 0
