"""채팅 실행 파이프라인 상태 관리."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# ── Tool 레이블 매핑 (히스토리 표시용) ────────────────────────────────────────
_TOOL_LABEL: dict[str, str] = {
    "get_row_count":   "행수조회",
    "analyze_missing": "결측치분석",
    "get_profile":     "프로파일",
    "aggregate_data":  "집계",
    "filter_rows":     "필터",
    "sort_rows":       "정렬",
    "filter_then_sort": "필터+정렬",
    "merge_files":       "병합",
    "merge_same_format": "동일양식통합",
    "create_chart":      "차트",
    "export_data":     "저장",
    "describe_data":   "요약",
}


class PipelineStage(str, Enum):
    INTENT          = "intent"
    PERSONA         = "persona"
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

    def to_dict(self) -> dict:
        return {
            "stage":       self.stage.value,
            "duration_ms": self.duration_ms,
            "details":     self.details,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StageMetrics":
        m = cls(stage=PipelineStage(d.get("stage", "intent")))
        m.duration_ms = int(d.get("duration_ms", 0))
        m.details     = dict(d.get("details", {}))
        return m


@dataclass
class PipelineState:
    # 입력
    user_prompt: str = ""

    # 분류
    intent: str = ""
    mode: str = "code"        # "llm" | "tool" | "code"
    task_config: dict = field(default_factory=dict)
    # task_config 예:
    # {
    #   "mode": "tool",
    #   "tool": "aggregate_data",
    #   "needs_chart": True,
    #   "needs_summary": False,
    #   "needs_export": False,
    #   "confidence": 0.92,
    # }
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

    def to_dict(self) -> dict:
        """채팅 영속화용 직렬화. thinking 패널 렌더링에 필요한 필드만 보존."""
        return {
            "user_prompt":             self.user_prompt,
            "intent":                  self.intent,
            "mode":                    self.mode,
            "task_config":             self.task_config,
            "persona_key":             self.persona_key,
            "persona_name":            self.persona_name,
            "system_prompt":           self.system_prompt,
            "system_prompt_token_est": self.system_prompt_token_est,
            "model_name":              self.model_name,
            "provider":                self.provider,
            "response_token_est":      self.response_token_est,
            "generated_code":          self.generated_code,
            "code_explanation":        self.code_explanation,
            "has_code":                self.has_code,
            "current_stage":           self.current_stage.value,
            "stages":                  [s.to_dict() for s in self.stages],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineState":
        s = cls(user_prompt=d.get("user_prompt", ""))
        s.intent                  = d.get("intent", "")
        s.mode                    = d.get("mode", "code")
        s.task_config             = dict(d.get("task_config", {}))
        s.persona_key             = d.get("persona_key", "")
        s.persona_name            = d.get("persona_name", "")
        s.system_prompt           = d.get("system_prompt", "")
        s.system_prompt_token_est = int(d.get("system_prompt_token_est", 0))
        s.model_name              = d.get("model_name", "")
        s.provider                = d.get("provider", "")
        s.response_token_est      = int(d.get("response_token_est", 0))
        s.generated_code          = d.get("generated_code", "")
        s.code_explanation        = d.get("code_explanation", "")
        s.has_code                = bool(d.get("has_code", False))
        try:
            s.current_stage = PipelineStage(d.get("current_stage", "intent"))
        except ValueError:
            s.current_stage = PipelineStage.INTENT
        s.stages = [StageMetrics.from_dict(x) for x in d.get("stages", [])]
        return s


# ── 세션 수준 Tool 실행 히스토리 ──────────────────────────────────────────────

@dataclass
class ToolExecution:
    """단일 턴의 실행 기록."""
    turn: int
    mode: str                      # "llm" | "tool" | "code"
    tool_name: str                 # tool 모드: 도구 이름, 그 외: ""
    user_prompt: str               # 사용자 질문 앞 60자
    success: bool
    duration_ms: int
    result_rows: int | None        # 결과 DataFrame 행 수 (없으면 None)
    chained: bool                  # use_last_result 체이닝 여부
    timestamp: datetime = field(default_factory=datetime.now)

    def label(self) -> str:
        if self.mode == "tool":
            return _TOOL_LABEL.get(self.tool_name, self.tool_name)
        if self.mode == "code":
            return "코드실행"
        return "LLM응답"


@dataclass
class SessionHistory:
    """세션 전체 실행 이력 레지스트리."""
    executions: list[ToolExecution] = field(default_factory=list)

    def record(self, ex: ToolExecution) -> None:
        self.executions.append(ex)

    def chain_str(self, last_n: int = 6) -> str:
        """최근 last_n개 성공 실행의 레이블을 '→'로 연결."""
        labels = [e.label() for e in self.executions[-last_n:] if e.success]
        return " → ".join(labels) if labels else ""

    def tool_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self.executions:
            lbl = e.label()
            counts[lbl] = counts.get(lbl, 0) + 1
        return counts

    def success_rate(self) -> float:
        if not self.executions:
            return 0.0
        return sum(1 for e in self.executions if e.success) / len(self.executions)

    def total(self) -> int:
        return len(self.executions)
