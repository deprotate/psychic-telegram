from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


NonEmptyStr = Annotated[str, Field(min_length=1)]


class BaseSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ReferenceItem(BaseSchema):
    id: str
    title: str
    source_type: str
    reason: str


class ScoreCriterion(BaseSchema):
    name: str
    score: int = Field(ge=0, le=100)
    rationale: str | None = None


class BusinessCaseSummary(BaseSchema):
    id: str
    title: str
    theme: str
    short_description: str
    difficulty: str
    tags: list[str] = Field(default_factory=list)


class BusinessCaseDetail(BusinessCaseSummary):
    background: str
    task: str
    reference_solution_summary: str
    evaluation_criteria: list[str] = Field(default_factory=list)


class IdeaSessionCreate(BaseSchema):
    client_id: NonEmptyStr
    idea_text: NonEmptyStr
    context: str | None = None


class SessionMessageCreate(BaseSchema):
    client_id: NonEmptyStr
    message: NonEmptyStr


class CaseSessionCreate(BaseSchema):
    client_id: NonEmptyStr
    case_id: NonEmptyStr


class CaseSubmitRequest(BaseSchema):
    client_id: NonEmptyStr
    solution_text: NonEmptyStr


class AIMessageResponse(BaseSchema):
    session_id: str
    reply: str
    used_references: list[ReferenceItem] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)


class CaseSessionResponse(BaseSchema):
    session_id: str
    case: BusinessCaseDetail
    welcome_message: str


class CaseEvaluationResponse(BaseSchema):
    session_id: str
    summary: str
    score: int = Field(ge=0, le=100)
    criteria_scores: list[ScoreCriterion] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    novel_ideas: list[str] = Field(default_factory=list)
    used_references: list[ReferenceItem] = Field(default_factory=list)


class CompletionRecord(BaseSchema):
    client_id: str
    task_type: str
    task_id: str
    self_marked_complete: bool
    completed_at: str


class CompleteTaskRequest(BaseSchema):
    client_id: NonEmptyStr
    task_type: Literal["idea_session", "case_session", "case_submission"]
    task_id: NonEmptyStr
    self_marked_complete: bool = True


class StatsResponse(BaseSchema):
    client_id: str
    completed_count: int = 0
    sessions_count: int = 0
    average_score: float | None = None
    last_activity: str | None = None


class CompleteTaskResponse(BaseSchema):
    status: str
    completion: CompletionRecord
    stats: StatsResponse


class HealthResponse(BaseSchema):
    status: str
    llm_mode: str
    cases_count: int
    risk_patterns_count: int
