from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from main2 import MockCaseService, YandexCaseService, parse_bool_env
from schemas import BusinessCaseDetail, BusinessCaseSummary, ScoreCriterion
from services import JsonRepository, utc_now_iso


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", BASE_DIR / "data"))


class BaseSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class TestHealthResponse(BaseSchema):
    status: str
    mode: str
    ready: bool
    error: str | None = None
    cases_count: int


class TestModeSwitchRequest(BaseSchema):
    mode: str = Field(pattern="^(mock|yandex)$")


class TestModeSwitchResponse(BaseSchema):
    status: str
    mode: str
    ready: bool
    error: str | None = None


class TestMessage(BaseSchema):
    role: str
    content: str


class ClientScopedRequest(BaseSchema):
    client_id: str = Field(min_length=1)


class TestCaseStartRequest(ClientScopedRequest):
    case_id: str = Field(min_length=1)


class TestCaseSubmitRequest(ClientScopedRequest):
    solution_text: str = Field(min_length=1)


class TestCaseFollowupRequest(ClientScopedRequest):
    message: str = Field(min_length=1)


class TestCaseProgressMarkRequest(ClientScopedRequest):
    case_id: str = Field(min_length=1)


class TestCaseEvaluationResponse(BaseSchema):
    mode: str
    case: BusinessCaseDetail
    summary: str
    score: int = Field(ge=0, le=100)
    criteria_scores: list[ScoreCriterion] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    novel_ideas: list[str] = Field(default_factory=list)
    messages: list[TestMessage] = Field(default_factory=list)


class TestCaseFollowupResponse(BaseSchema):
    mode: str
    case: BusinessCaseDetail
    reply: str
    risks: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    messages: list[TestMessage] = Field(default_factory=list)


class TestCaseStartResponse(BaseSchema):
    mode: str
    case: BusinessCaseDetail
    welcome_message: str
    messages: list[TestMessage] = Field(default_factory=list)


class TestCaseStateResponse(BaseSchema):
    mode: str
    active_case: BusinessCaseDetail | None = None
    messages: list[TestMessage] = Field(default_factory=list)
    last_evaluation: TestCaseEvaluationResponse | None = None


class TestCasesProgressResponse(BaseSchema):
    solved_cases: list[BusinessCaseSummary] = Field(default_factory=list)
    unsolved_cases: list[BusinessCaseSummary] = Field(default_factory=list)
    solved_count: int
    unsolved_count: int


class TestCasesProgressMutationResponse(TestCasesProgressResponse):
    status: str


def create_test_state() -> dict[str, Any]:
    timestamp = utc_now_iso()
    return {
        "active_case_id": None,
        "messages": [],
        "last_solution": None,
        "last_evaluation": None,
        "solved_case_ids": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def normalize_test_state(raw_state: Any) -> dict[str, Any]:
    state = create_test_state()
    if not isinstance(raw_state, dict):
        return state

    active_case_id = raw_state.get("active_case_id")
    if isinstance(active_case_id, str) and active_case_id.strip():
        state["active_case_id"] = active_case_id

    messages = raw_state.get("messages")
    if isinstance(messages, list):
        cleaned_messages = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if isinstance(role, str) and isinstance(content, str):
                cleaned_messages.append({"role": role, "content": content})
        state["messages"] = cleaned_messages

    state["last_solution"] = raw_state.get("last_solution")
    if isinstance(raw_state.get("last_evaluation"), dict):
        state["last_evaluation"] = raw_state["last_evaluation"]

    solved_case_ids = raw_state.get("solved_case_ids")
    if isinstance(solved_case_ids, list):
        state["solved_case_ids"] = [str(item) for item in solved_case_ids if str(item).strip()]

    created_at = raw_state.get("created_at")
    updated_at = raw_state.get("updated_at")
    if isinstance(created_at, str) and created_at.strip():
        state["created_at"] = created_at
    if isinstance(updated_at, str) and updated_at.strip():
        state["updated_at"] = updated_at

    return state


def touch_state(state: dict[str, Any]) -> dict[str, Any]:
    if not state.get("created_at"):
        state["created_at"] = utc_now_iso()
    state["updated_at"] = utc_now_iso()
    return state


def create_main3_app(repository: JsonRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="AI Business Trainer Multi-User Test API",
        version="0.3.0",
        description="Multi-user test API для тренажёра бизнес-кейсов с изоляцией по client_id.",
    )

    cors_origins = [item.strip() for item in os.getenv("APP_CORS_ORIGINS", "*").split(",") if item.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.repository = repository or JsonRepository(DATA_DIR)

    def configure_mode(mode: str) -> None:
        app.state.mode = mode
        app.state.service_error = None

        if mode == "mock":
            app.state.case_service = MockCaseService()
            return

        api_key = os.getenv("YANDEX_API_KEY")
        folder_id = os.getenv("YANDEX_FOLDER_ID")

        if api_key and folder_id:
            app.state.case_service = YandexCaseService(api_key=api_key, folder_id=folder_id)
        else:
            app.state.case_service = None
            app.state.service_error = "YANDEX_API_KEY and YANDEX_FOLDER_ID are required when mode=yandex"

    use_mock = parse_bool_env("TEST_USE_MOCK", default=False)
    configure_mode("mock" if use_mock else "yandex")

    def get_repository() -> JsonRepository:
        return app.state.repository

    def get_service() -> MockCaseService | YandexCaseService:
        service = app.state.case_service
        if service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=app.state.service_error or "Case service is not configured",
            )
        return service

    def get_case_or_404(case_id: str) -> dict[str, Any]:
        case_data = get_repository().get_case(case_id)
        if not case_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        return case_data

    def get_client_state(client_id: str) -> dict[str, Any]:
        return normalize_test_state(get_repository().get_test_case_state(client_id))

    def save_client_state(client_id: str, state: dict[str, Any]) -> dict[str, Any]:
        return get_repository().save_test_case_state(client_id, touch_state(state))

    def get_active_case_or_400(state: dict[str, Any]) -> dict[str, Any]:
        active_case_id = state.get("active_case_id")
        if not active_case_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active test case for this client. Start one first.",
            )
        return get_case_or_404(active_case_id)

    def serialize_messages(state: dict[str, Any]) -> list[TestMessage]:
        return [TestMessage(role=item["role"], content=item["content"]) for item in state.get("messages", [])]

    def build_progress_payload(state: dict[str, Any]) -> dict[str, Any]:
        all_cases = get_repository().list_cases()
        solved_ids = {str(item) for item in state.get("solved_case_ids", [])}
        solved_cases = [BusinessCaseSummary.model_validate(item) for item in all_cases if item["id"] in solved_ids]
        unsolved_cases = [BusinessCaseSummary.model_validate(item) for item in all_cases if item["id"] not in solved_ids]
        return {
            "solved_cases": solved_cases,
            "unsolved_cases": unsolved_cases,
            "solved_count": len(solved_cases),
            "unsolved_count": len(unsolved_cases),
        }

    def build_state_response(client_id: str) -> TestCaseStateResponse:
        state = get_client_state(client_id)
        active_case_id = state.get("active_case_id")
        active_case = BusinessCaseDetail.model_validate(get_case_or_404(active_case_id)) if active_case_id else None
        evaluation = state.get("last_evaluation")
        last_evaluation = None
        if evaluation and active_case:
            last_evaluation = TestCaseEvaluationResponse(
                mode=app.state.mode,
                case=active_case,
                summary=evaluation["summary"],
                score=evaluation["score"],
                criteria_scores=evaluation["criteria_scores"],
                strengths=evaluation["strengths"],
                weaknesses=evaluation["weaknesses"],
                improvements=evaluation["improvements"],
                novel_ideas=evaluation["novel_ideas"],
                messages=serialize_messages(state),
            )
        return TestCaseStateResponse(
            mode=app.state.mode,
            active_case=active_case,
            messages=serialize_messages(state),
            last_evaluation=last_evaluation,
        )

    @app.get("/test3/health", response_model=TestHealthResponse)
    def health() -> TestHealthResponse:
        return TestHealthResponse(
            status="ok" if app.state.case_service is not None else "misconfigured",
            mode=app.state.mode,
            ready=app.state.case_service is not None,
            error=app.state.service_error,
            cases_count=len(get_repository().list_cases()),
        )

    @app.post("/test3/mode", response_model=TestModeSwitchResponse)
    def switch_mode(payload: TestModeSwitchRequest) -> TestModeSwitchResponse:
        configure_mode(payload.mode)
        return TestModeSwitchResponse(
            status="ok" if app.state.case_service is not None else "misconfigured",
            mode=app.state.mode,
            ready=app.state.case_service is not None,
            error=app.state.service_error,
        )

    @app.get("/test3/cases", response_model=list[BusinessCaseSummary])
    def list_cases() -> list[BusinessCaseSummary]:
        return [BusinessCaseSummary.model_validate(item) for item in get_repository().list_cases()]

    @app.get("/test3/cases/progress", response_model=TestCasesProgressResponse)
    def get_cases_progress(client_id: str = Query(min_length=1)) -> TestCasesProgressResponse:
        return TestCasesProgressResponse(**build_progress_payload(get_client_state(client_id)))

    @app.post("/test3/cases/progress/mark-solved", response_model=TestCasesProgressMutationResponse)
    def mark_case_solved(payload: TestCaseProgressMarkRequest) -> TestCasesProgressMutationResponse:
        get_case_or_404(payload.case_id)
        state = get_client_state(payload.client_id)
        solved_ids = {str(item) for item in state.get("solved_case_ids", [])}
        solved_ids.add(payload.case_id)
        state["solved_case_ids"] = sorted(solved_ids)
        save_client_state(payload.client_id, state)
        return TestCasesProgressMutationResponse(status="ok", **build_progress_payload(state))

    @app.post("/test3/cases/progress/unmark-solved", response_model=TestCasesProgressMutationResponse)
    def unmark_case_solved(payload: TestCaseProgressMarkRequest) -> TestCasesProgressMutationResponse:
        get_case_or_404(payload.case_id)
        state = get_client_state(payload.client_id)
        solved_ids = {str(item) for item in state.get("solved_case_ids", [])}
        solved_ids.discard(payload.case_id)
        state["solved_case_ids"] = sorted(solved_ids)
        save_client_state(payload.client_id, state)
        return TestCasesProgressMutationResponse(status="ok", **build_progress_payload(state))

    @app.post("/test3/cases/progress/reset", response_model=TestCasesProgressMutationResponse)
    def reset_cases_progress(payload: ClientScopedRequest) -> TestCasesProgressMutationResponse:
        state = get_client_state(payload.client_id)
        state["solved_case_ids"] = []
        save_client_state(payload.client_id, state)
        return TestCasesProgressMutationResponse(status="ok", **build_progress_payload(state))

    @app.get("/test3/cases/{case_id}", response_model=BusinessCaseDetail)
    def get_case(case_id: str) -> BusinessCaseDetail:
        return BusinessCaseDetail.model_validate(get_case_or_404(case_id))

    @app.get("/test3/case/state", response_model=TestCaseStateResponse)
    def get_case_state(client_id: str = Query(min_length=1)) -> TestCaseStateResponse:
        return build_state_response(client_id)

    @app.post("/test3/case/start", response_model=TestCaseStartResponse)
    def start_case(payload: TestCaseStartRequest) -> TestCaseStartResponse:
        case_data = get_case_or_404(payload.case_id)
        get_service()

        existing_state = get_client_state(payload.client_id)
        state = create_test_state()
        state["solved_case_ids"] = list(dict.fromkeys(existing_state.get("solved_case_ids", [])))
        state["created_at"] = existing_state.get("created_at") or state["created_at"]
        state["active_case_id"] = payload.case_id
        welcome_message = (
            f"Кейс «{case_data['title']}» активирован. "
            "Пришли решение, и я оценю его и подскажу, как доработать."
        )
        state["messages"] = [{"role": "assistant", "content": welcome_message}]
        save_client_state(payload.client_id, state)

        return TestCaseStartResponse(
            mode=app.state.mode,
            case=BusinessCaseDetail.model_validate(case_data),
            welcome_message=welcome_message,
            messages=serialize_messages(state),
        )

    @app.post("/test3/case/submit", response_model=TestCaseEvaluationResponse)
    def submit_case(payload: TestCaseSubmitRequest) -> TestCaseEvaluationResponse:
        service = get_service()
        state = get_client_state(payload.client_id)
        case_data = get_active_case_or_400(state)
        history = [*state["messages"], {"role": "user", "content": payload.solution_text}]

        try:
            evaluation = service.evaluate_case_solution(case_data=case_data, solution_text=payload.solution_text, history=history)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        state["last_solution"] = payload.solution_text
        state["last_evaluation"] = evaluation
        solved_ids = {str(item) for item in state.get("solved_case_ids", [])}
        solved_ids.add(case_data["id"])
        state["solved_case_ids"] = sorted(solved_ids)
        state["messages"].append({"role": "user", "content": payload.solution_text})
        state["messages"].append({"role": "assistant", "content": evaluation["summary"]})
        save_client_state(payload.client_id, state)

        return TestCaseEvaluationResponse(
            mode=app.state.mode,
            case=BusinessCaseDetail.model_validate(case_data),
            summary=evaluation["summary"],
            score=evaluation["score"],
            criteria_scores=evaluation["criteria_scores"],
            strengths=evaluation["strengths"],
            weaknesses=evaluation["weaknesses"],
            improvements=evaluation["improvements"],
            novel_ideas=evaluation["novel_ideas"],
            messages=serialize_messages(state),
        )

    @app.post("/test3/case/followup", response_model=TestCaseFollowupResponse)
    def case_followup(payload: TestCaseFollowupRequest) -> TestCaseFollowupResponse:
        service = get_service()
        state = get_client_state(payload.client_id)
        case_data = get_active_case_or_400(state)
        if not state.get("last_evaluation"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Submit a solution before asking follow-up questions.",
            )

        history = [*state["messages"], {"role": "user", "content": payload.message}]
        try:
            answer = service.answer_case_followup(
                case_data=case_data,
                question=payload.message,
                history=history,
                evaluation=state["last_evaluation"],
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        state["messages"].append({"role": "user", "content": payload.message})
        state["messages"].append({"role": "assistant", "content": answer["reply"]})
        save_client_state(payload.client_id, state)

        return TestCaseFollowupResponse(
            mode=app.state.mode,
            case=BusinessCaseDetail.model_validate(case_data),
            reply=answer["reply"],
            risks=answer["risks"],
            next_questions=answer["next_questions"],
            advice=answer["advice"],
            messages=serialize_messages(state),
        )

    return app


app = create_main3_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main3:app", reload=True)
