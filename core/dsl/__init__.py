"""DataFrame DSL — LLM이 생성하는 파이프라인을 결정적으로 실행.

기존 도구 함수와 독립된 모듈. 점진적으로 키워드 라우터·도구 함수를 대체.
- spec.py:       op 명세, 검증, LLM에 노출할 spec 생성
- interpreter.py: pipeline 받아 op 순차 실행
"""
from core.dsl.interpreter import run_pipeline
from core.dsl.spec import OPS, validate_pipeline, validate_pipeline_with_data, PipelineError

__all__ = ["run_pipeline", "OPS", "validate_pipeline",
           "validate_pipeline_with_data", "PipelineError"]
