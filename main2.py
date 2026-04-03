from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field

from schemas import BusinessCaseDetail, BusinessCaseSummary, ScoreCriterion
from services import JsonRepository


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", BASE_DIR / "data"))


def parse_bool_env(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower()))


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


class TestCaseStartRequest(BaseSchema):
    case_id: str = Field(min_length=1)


class TestCaseSubmitRequest(BaseSchema):
    solution_text: str = Field(min_length=1)


class TestCaseFollowupRequest(BaseSchema):
    message: str = Field(min_length=1)


class TestCaseProgressMarkRequest(BaseSchema):
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


class MockCaseService:
    mode = "mock"

    def evaluate_case_solution(
        self,
        case_data: dict[str, Any],
        solution_text: str,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        reference_tokens = tokenize(case_data.get("reference_solution_summary", ""))
        solution_tokens = tokenize(solution_text)
        overlap = len(reference_tokens & solution_tokens)
        novelty_tokens = solution_tokens - reference_tokens
        score = min(95, 52 + overlap * 4)
        if len(solution_text.split()) < 25:
            score = max(30, score - 15)

        criteria = [
            {"name": "problem_clarity", "score": max(35, min(95, score + 2)), "rationale": "Есть ли ясная постановка задачи."},
            {"name": "market_business_logic", "score": max(35, min(95, score)), "rationale": "Насколько убедительна бизнес-логика."},
            {"name": "feasibility", "score": max(35, min(95, score - 4)), "rationale": "Насколько реалистичен первый шаг."},
            {"name": "differentiation", "score": max(35, min(95, score + 1)), "rationale": "Есть ли сильное отличие от альтернатив."},
        ]

        novel_ideas = []
        if novelty_tokens:
            novel_ideas.append("В решении есть свои идеи относительно эталона, и это плюс, если их можно защитить цифрами.")

        return {
            "summary": (
                f"Решение по кейсу «{case_data['title']}» выглядит рабочим, "
                "но ему не хватает большей конкретики по метрикам, приоритетам и плану проверки."
            ),
            "score": score,
            "criteria_scores": criteria,
            "strengths": [
                "Ответ структурирован и пытается связать проблему с решением.",
                "Видно стремление к MVP-подходу, а не к абстрактной стратегии.",
            ],
            "weaknesses": [
                "Недостаёт более чётких метрик успеха и условий провала.",
                "Слабо раскрыты ограничения и риски внедрения.",
            ],
            "improvements": [
                "Добавьте 2-3 метрики и срок их проверки.",
                "Покажите первый эксперимент, который можно сделать быстро и дёшево.",
                "Явно объясните, почему выбранный подход сильнее альтернатив.",
            ],
            "novel_ideas": novel_ideas,
        }

    def answer_case_followup(
        self,
        case_data: dict[str, Any],
        question: str,
        history: list[dict[str, str]],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        score = evaluation.get("score")
        reply = (
            f"Если докручивать кейс «{case_data['title']}», я бы сейчас сфокусировался на одном эксперименте, "
            "который быстрее всего подтвердит или опровергнет твою главную гипотезу."
        )
        if score is not None:
            reply += f" Текущее решение выглядит примерно на {score}/100, и основной рост даст больше конкретики."

        return {
            "reply": reply,
            "risks": [
                "Ответ может остаться слишком общим без чёткой последовательности шагов.",
                "Есть риск недооценить ограничения запуска и стоимость эксперимента.",
            ],
            "next_questions": [
                f"Какой один эксперимент лучше всего отвечает на вопрос: {question}",
                "Какая метрика честно покажет, что твоя гипотеза не работает?",
            ],
            "advice": [
                "Опиши эксперимент в формате гипотеза -> действие -> метрика -> срок.",
                "Привяжи рекомендацию к ограничениям самого кейса, а не к абстрактной стратегии.",
            ],
        }


class YandexCaseService:
    mode = "yandex"

    def __init__(self, api_key: str, folder_id: str, model_name: str = "yandexgpt-5-pro") -> None:
        self.folder_id = folder_id
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key, base_url="https://ai.api.cloud.yandex.net/v1")

    def evaluate_case_solution(
        self,
        case_data: dict[str, Any],
        solution_text: str,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        payload = {
            "case": case_data,
            "solution_text": solution_text,
            "history": history,
            "output_schema": {
                "summary": "string",
                "score": "integer 0-100",
                "criteria_scores": [{"name": "string", "score": "integer 0-100", "rationale": "string"}],
                "strengths": ["string"],
                "weaknesses": ["string"],
                "improvements": ["string"],
                "novel_ideas": ["string"],
            },
        }
        response = self._chat_json(
            system_prompt=(
                "Ты оцениваешь решение бизнес-кейса. "
                "Отвечай строго валидным JSON, честно оценивай сильные и слабые стороны, "
                "а эталон используй как ориентир, а не как единственно верный шаблон."
            ),
            payload=payload,
        )
        return self._normalize_evaluation(response)

    def answer_case_followup(
        self,
        case_data: dict[str, Any],
        question: str,
        history: list[dict[str, str]],
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "case": case_data,
            "question": question,
            "history": history,
            "last_evaluation": evaluation,
            "output_schema": {
                "reply": "string",
                "risks": ["string"],
                "next_questions": ["string"],
                "advice": ["string"],
            },
        }
        response = self._chat_json(
            system_prompt=(
                "Ты помогаешь доработать решение бизнес-кейса после первичной оценки. "
                "Отвечай строго валидным JSON без markdown и воды."
            ),
            payload=payload,
        )
        return self._normalize_followup(response)

    def _chat_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.chat.completions.create(
                model=f"gpt://{self.folder_id}/{self.model_name}",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Ответь строго валидным JSON без markdown и без пояснений. "
                            f"Данные:\n{json.dumps(payload, ensure_ascii=False)}"
                        ),
                    },
                ],
                temperature=0.4,
                max_tokens=1600,
            )
        except Exception as exc:
            raise RuntimeError(f"Yandex API request failed: {exc}") from exc

        content = response.choices[0].message.content or ""
        data = self._extract_json(content)
        if data is None:
            raise RuntimeError("Yandex API returned non-JSON response")
        return data

    def _extract_json(self, content: str) -> dict[str, Any] | None:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, flags=re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    def _normalize_evaluation(self, payload: dict[str, Any]) -> dict[str, Any]:
        score = self._normalize_score(payload.get("score"))
        criteria_scores = []
        for item in payload.get("criteria_scores", []):
            if not isinstance(item, dict):
                continue
            criteria_scores.append(
                {
                    "name": str(item.get("name") or "criterion"),
                    "score": self._normalize_score(item.get("score")),
                    "rationale": item.get("rationale"),
                }
            )
        if not criteria_scores:
            criteria_scores = [
                {"name": "problem_clarity", "score": score, "rationale": None},
                {"name": "market_business_logic", "score": score, "rationale": None},
                {"name": "feasibility", "score": score, "rationale": None},
                {"name": "differentiation", "score": score, "rationale": None},
            ]

        return {
            "summary": str(payload.get("summary") or "Модель вернула оценку без summary."),
            "score": score,
            "criteria_scores": criteria_scores,
            "strengths": self._normalize_list(payload.get("strengths")),
            "weaknesses": self._normalize_list(payload.get("weaknesses")),
            "improvements": self._normalize_list(payload.get("improvements")),
            "novel_ideas": self._normalize_list(payload.get("novel_ideas")),
        }

    def _normalize_followup(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "reply": str(payload.get("reply") or "Модель не вернула содержательный follow-up ответ."),
            "risks": self._normalize_list(payload.get("risks")),
            "next_questions": self._normalize_list(payload.get("next_questions")),
            "advice": self._normalize_list(payload.get("advice")),
        }

    def _normalize_score(self, value: Any) -> int:
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return 0

    def _normalize_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]


def create_test_state() -> dict[str, Any]:
    return {
        "active_case_id": None,
        "messages": [],
        "last_solution": None,
        "last_evaluation": None,
        "solved_case_ids": set(),
    }


def create_main2_app(repository: JsonRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="AI Business Trainer Test API",
        version="0.1.0",
        description="Упрощённый test API без id и multi-session логики.",
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
    app.state.test_state = create_test_state()

    def configure_mode(mode: str) -> None:
        app.state.mode = mode
        app.state.service_error = None

        if mode == "mock":
            app.state.case_service = MockCaseService()
            return

        api_key = os.getenv("YANDEX_API_KEY", "AQVN164qFPx2CKKmz9OreO_zs9s9FAn4mZ9qz69D")
        folder_id = os.getenv("YANDEX_FOLDER_ID", "b1grlh2bqatdjmcl9tt0")

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

    def get_active_case_or_400() -> dict[str, Any]:
        active_case_id = app.state.test_state.get("active_case_id")
        if not active_case_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active test case. Start one first.")
        return get_case_or_404(active_case_id)

    def serialize_messages() -> list[TestMessage]:
        return [TestMessage(role=item["role"], content=item["content"]) for item in app.state.test_state.get("messages", [])]

    def build_progress_payload() -> dict[str, Any]:
        all_cases = get_repository().list_cases()
        solved_ids = set(app.state.test_state.get("solved_case_ids", set()))
        solved_cases = [BusinessCaseSummary.model_validate(item) for item in all_cases if item["id"] in solved_ids]
        unsolved_cases = [BusinessCaseSummary.model_validate(item) for item in all_cases if item["id"] not in solved_ids]
        return {
            "solved_cases": solved_cases,
            "unsolved_cases": unsolved_cases,
            "solved_count": len(solved_cases),
            "unsolved_count": len(unsolved_cases),
        }

    def build_state_response() -> TestCaseStateResponse:
        active_case_id = app.state.test_state.get("active_case_id")
        active_case = BusinessCaseDetail.model_validate(get_case_or_404(active_case_id)) if active_case_id else None
        evaluation = app.state.test_state.get("last_evaluation")
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
                messages=serialize_messages(),
            )
        return TestCaseStateResponse(
            mode=app.state.mode,
            active_case=active_case,
            messages=serialize_messages(),
            last_evaluation=last_evaluation,
        )

    @app.get("/test/health", response_model=TestHealthResponse)
    def health() -> TestHealthResponse:
        return TestHealthResponse(
            status="ok" if app.state.case_service is not None else "misconfigured",
            mode=app.state.mode,
            ready=app.state.case_service is not None,
            error=app.state.service_error,
            cases_count=len(get_repository().list_cases()),
        )

    @app.post("/test/mode", response_model=TestModeSwitchResponse)
    def switch_mode(payload: TestModeSwitchRequest) -> TestModeSwitchResponse:
        configure_mode(payload.mode)
        return TestModeSwitchResponse(
            status="ok" if app.state.case_service is not None else "misconfigured",
            mode=app.state.mode,
            ready=app.state.case_service is not None,
            error=app.state.service_error,
        )

    @app.get("/test/cases", response_model=list[BusinessCaseSummary])
    def list_cases() -> list[BusinessCaseSummary]:
        return [BusinessCaseSummary.model_validate(item) for item in get_repository().list_cases()]

    @app.get("/test/cases/progress", response_model=TestCasesProgressResponse)
    def get_cases_progress() -> TestCasesProgressResponse:
        return TestCasesProgressResponse(**build_progress_payload())

    @app.post("/test/cases/progress/mark-solved", response_model=TestCasesProgressMutationResponse)
    def mark_case_solved(payload: TestCaseProgressMarkRequest) -> TestCasesProgressMutationResponse:
        get_case_or_404(payload.case_id)
        app.state.test_state["solved_case_ids"].add(payload.case_id)
        return TestCasesProgressMutationResponse(status="ok", **build_progress_payload())

    @app.post("/test/cases/progress/unmark-solved", response_model=TestCasesProgressMutationResponse)
    def unmark_case_solved(payload: TestCaseProgressMarkRequest) -> TestCasesProgressMutationResponse:
        get_case_or_404(payload.case_id)
        app.state.test_state["solved_case_ids"].discard(payload.case_id)
        return TestCasesProgressMutationResponse(status="ok", **build_progress_payload())

    @app.post("/test/cases/progress/reset", response_model=TestCasesProgressMutationResponse)
    def reset_cases_progress() -> TestCasesProgressMutationResponse:
        app.state.test_state["solved_case_ids"] = set()
        return TestCasesProgressMutationResponse(status="ok", **build_progress_payload())

    @app.get("/test/cases/{case_id}", response_model=BusinessCaseDetail)
    def get_case(case_id: str) -> BusinessCaseDetail:
        return BusinessCaseDetail.model_validate(get_case_or_404(case_id))

    @app.get("/test/case/state", response_model=TestCaseStateResponse)
    def get_case_state() -> TestCaseStateResponse:
        return build_state_response()

    @app.post("/test/case/start", response_model=TestCaseStartResponse)
    def start_case(payload: TestCaseStartRequest) -> TestCaseStartResponse:
        case_data = get_case_or_404(payload.case_id)
        get_service()
        solved_case_ids = set(app.state.test_state.get("solved_case_ids", set()))
        app.state.test_state = create_test_state()
        app.state.test_state["solved_case_ids"] = solved_case_ids
        app.state.test_state["active_case_id"] = payload.case_id
        welcome_message = (
            f"Кейс «{case_data['title']}» активирован. "
            "Пришли решение, и я оценю его и подскажу, как доработать."
        )
        app.state.test_state["messages"] = [{"role": "assistant", "content": welcome_message}]
        return TestCaseStartResponse(
            mode=app.state.mode,
            case=BusinessCaseDetail.model_validate(case_data),
            welcome_message=welcome_message,
            messages=serialize_messages(),
        )

    @app.post("/test/case/submit", response_model=TestCaseEvaluationResponse)
    def submit_case(payload: TestCaseSubmitRequest) -> TestCaseEvaluationResponse:
        service = get_service()
        case_data = get_active_case_or_400()
        history = [*app.state.test_state["messages"], {"role": "user", "content": payload.solution_text}]
        try:
            evaluation = service.evaluate_case_solution(case_data=case_data, solution_text=payload.solution_text, history=history)
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        app.state.test_state["last_solution"] = payload.solution_text
        app.state.test_state["last_evaluation"] = evaluation
        app.state.test_state["solved_case_ids"].add(case_data["id"])
        app.state.test_state["messages"].append({"role": "user", "content": payload.solution_text})
        app.state.test_state["messages"].append({"role": "assistant", "content": evaluation["summary"]})

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
            messages=serialize_messages(),
        )

    @app.post("/test/case/followup", response_model=TestCaseFollowupResponse)
    def case_followup(payload: TestCaseFollowupRequest) -> TestCaseFollowupResponse:
        service = get_service()
        case_data = get_active_case_or_400()
        if not app.state.test_state.get("last_evaluation"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Submit a solution before asking follow-up questions.",
            )

        history = [*app.state.test_state["messages"], {"role": "user", "content": payload.message}]
        try:
            answer = service.answer_case_followup(
                case_data=case_data,
                question=payload.message,
                history=history,
                evaluation=app.state.test_state["last_evaluation"],
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        app.state.test_state["messages"].append({"role": "user", "content": payload.message})
        app.state.test_state["messages"].append({"role": "assistant", "content": answer["reply"]})

        return TestCaseFollowupResponse(
            mode=app.state.mode,
            case=BusinessCaseDetail.model_validate(case_data),
            reply=answer["reply"],
            risks=answer["risks"],
            next_questions=answer["next_questions"],
            advice=answer["advice"],
            messages=serialize_messages(),
        )

    return app


app = create_main2_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main2:app", reload=True)
