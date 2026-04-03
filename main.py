from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    AIMessageResponse,
    BusinessCaseDetail,
    BusinessCaseSummary,
    CaseEvaluationResponse,
    CaseSessionCreate,
    CaseSessionResponse,
    CaseSubmitRequest,
    CompleteTaskRequest,
    CompleteTaskResponse,
    HealthResponse,
    IdeaSessionCreate,
    SessionMessageCreate,
    StatsResponse,
)
from services import (
    BusinessTrainerAIService,
    JsonRepository,
    append_session_message,
    build_case_reference,
    build_reference_items,
    create_session_record,
    utc_now_iso,
)


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", BASE_DIR / "data"))


def create_app(
    repository: JsonRepository | None = None,
    ai_service: BusinessTrainerAIService | None = None,
) -> FastAPI:
    app = FastAPI(
        title="AI Business Trainer MVP",
        version="0.1.0",
        description="FastAPI MVP для тренажёра бизнес-кейсов и разбора стартап-идей с ИИ-ассистентом.",
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
    app.state.ai_service = ai_service or BusinessTrainerAIService()

    def get_repository() -> JsonRepository:
        return app.state.repository

    def get_ai_service() -> BusinessTrainerAIService:
        return app.state.ai_service

    def get_case_or_404(case_id: str) -> dict:
        case_data = get_repository().get_case(case_id)
        if not case_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        return case_data

    def get_session_or_404(session_id: str) -> dict:
        session = get_repository().get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return session

    def ensure_session_owner(session: dict, client_id: str) -> None:
        if session.get("client_id") != client_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session belongs to another client")

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        repository = get_repository()
        service = get_ai_service()
        return HealthResponse(
            status="ok",
            llm_mode=service.mode,
            cases_count=len(repository.list_cases()),
            risk_patterns_count=len(repository.list_risk_patterns()),
        )

    @app.get("/api/v1/cases", response_model=list[BusinessCaseSummary])
    def list_cases() -> list[BusinessCaseSummary]:
        return [BusinessCaseSummary.model_validate(case_data) for case_data in get_repository().list_cases()]

    @app.get("/api/v1/cases/{case_id}", response_model=BusinessCaseDetail)
    def get_case(case_id: str) -> BusinessCaseDetail:
        return BusinessCaseDetail.model_validate(get_case_or_404(case_id))

    @app.post("/api/v1/idea-sessions", response_model=AIMessageResponse, status_code=status.HTTP_201_CREATED)
    def create_idea_session(payload: IdeaSessionCreate) -> AIMessageResponse:
        repository = get_repository()
        service = get_ai_service()
        references = build_reference_items(
            idea_text=payload.idea_text,
            risk_patterns=repository.list_risk_patterns(),
            cases=repository.list_cases(),
        )

        session = create_session_record(
            client_id=payload.client_id,
            mode="idea",
            title=payload.idea_text[:80],
            idea_text=payload.idea_text,
            context=payload.context,
            used_references=references,
        )
        feedback = service.generate_idea_feedback(
            idea_text=payload.idea_text,
            context=payload.context,
            history=[],
            references=references,
        )

        append_session_message(session, "user", payload.idea_text)
        append_session_message(session, "assistant", feedback["reply"])
        repository.create_session(session)

        return AIMessageResponse(
            session_id=session["id"],
            reply=feedback["reply"],
            used_references=references,
            next_questions=feedback["next_questions"],
            risks=feedback["risks"],
            advice=feedback["advice"],
        )

    @app.post("/api/v1/idea-sessions/{session_id}/messages", response_model=AIMessageResponse)
    def continue_idea_session(session_id: str, payload: SessionMessageCreate) -> AIMessageResponse:
        repository = get_repository()
        service = get_ai_service()
        session = get_session_or_404(session_id)
        ensure_session_owner(session, payload.client_id)
        if session.get("mode") != "idea":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not an idea session")

        history = [*session.get("messages", []), {"role": "user", "content": payload.message}]
        feedback = service.generate_idea_feedback(
            idea_text=session.get("idea_text") or payload.message,
            context=session.get("context"),
            history=history,
            references=session.get("used_references", []),
        )

        append_session_message(session, "user", payload.message)
        append_session_message(session, "assistant", feedback["reply"])
        repository.save_session(session)

        return AIMessageResponse(
            session_id=session["id"],
            reply=feedback["reply"],
            used_references=session.get("used_references", []),
            next_questions=feedback["next_questions"],
            risks=feedback["risks"],
            advice=feedback["advice"],
        )

    @app.post("/api/v1/case-sessions", response_model=CaseSessionResponse, status_code=status.HTTP_201_CREATED)
    def create_case_session(payload: CaseSessionCreate) -> CaseSessionResponse:
        repository = get_repository()
        case_data = get_case_or_404(payload.case_id)
        session = create_session_record(
            client_id=payload.client_id,
            mode="case",
            title=case_data["title"],
            case_id=payload.case_id,
            used_references=build_case_reference(case_data),
        )
        append_session_message(
            session,
            "assistant",
            "Сессия по кейсу создана. Отправьте своё решение, и я разберу его по эталону и критериям оценки.",
        )
        repository.create_session(session)
        return CaseSessionResponse(
            session_id=session["id"],
            case=BusinessCaseDetail.model_validate(case_data),
            welcome_message=session["messages"][-1]["content"],
        )

    @app.post("/api/v1/case-sessions/{session_id}/submit", response_model=CaseEvaluationResponse)
    def submit_case_solution(session_id: str, payload: CaseSubmitRequest) -> CaseEvaluationResponse:
        repository = get_repository()
        service = get_ai_service()
        session = get_session_or_404(session_id)
        ensure_session_owner(session, payload.client_id)
        if session.get("mode") != "case":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not a case session")

        case_data = get_case_or_404(session["case_id"])
        evaluation = service.evaluate_case_solution(
            case_data=case_data,
            solution_text=payload.solution_text,
            history=session.get("messages", []),
        )

        append_session_message(session, "user", payload.solution_text)
        append_session_message(session, "assistant", evaluation["summary"])
        session["last_score"] = evaluation["score"]
        session["last_evaluation"] = evaluation
        session["updated_at"] = utc_now_iso()
        repository.save_session(session)

        return CaseEvaluationResponse(
            session_id=session["id"],
            summary=evaluation["summary"],
            score=evaluation["score"],
            criteria_scores=evaluation["criteria_scores"],
            strengths=evaluation["strengths"],
            weaknesses=evaluation["weaknesses"],
            improvements=evaluation["improvements"],
            novel_ideas=evaluation["novel_ideas"],
            used_references=session.get("used_references", []),
        )

    @app.post("/api/v1/case-sessions/{session_id}/messages", response_model=AIMessageResponse)
    def case_followup(session_id: str, payload: SessionMessageCreate) -> AIMessageResponse:
        repository = get_repository()
        service = get_ai_service()
        session = get_session_or_404(session_id)
        ensure_session_owner(session, payload.client_id)
        if session.get("mode") != "case":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not a case session")

        case_data = get_case_or_404(session["case_id"])
        answer = service.answer_case_followup(
            case_data=case_data,
            question=payload.message,
            history=session.get("messages", []),
            evaluation=session.get("last_evaluation"),
        )

        append_session_message(session, "user", payload.message)
        append_session_message(session, "assistant", answer["reply"])
        repository.save_session(session)

        return AIMessageResponse(
            session_id=session["id"],
            reply=answer["reply"],
            used_references=session.get("used_references", []),
            next_questions=answer["next_questions"],
            risks=answer["risks"],
            advice=answer["advice"],
        )

    @app.post("/api/v1/progress/complete", response_model=CompleteTaskResponse)
    def complete_task(payload: CompleteTaskRequest) -> CompleteTaskResponse:
        repository = get_repository()
        completion = repository.record_completion(
            {
                "client_id": payload.client_id,
                "task_type": payload.task_type,
                "task_id": payload.task_id,
                "self_marked_complete": payload.self_marked_complete,
                "completed_at": utc_now_iso(),
            }
        )
        stats = repository.get_stats(payload.client_id)
        return CompleteTaskResponse(status="ok", completion=completion, stats=stats)

    @app.get("/api/v1/stats/{client_id}", response_model=StatsResponse)
    def get_stats(client_id: str) -> StatsResponse:
        return StatsResponse.model_validate(get_repository().get_stats(client_id))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app",reload=True)
