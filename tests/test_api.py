from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import create_app
from services import JsonRepository


class FakeAIService:
    mode = "mock"

    def generate_idea_feedback(self, idea_text, context, history, references):
        return {
            "reply": f"Разбор идеи: {idea_text[:40]}",
            "risks": ["Риск спроса", "Риск экономики"],
            "next_questions": ["Кто первый сегмент?", "Как проверите спрос?"],
            "advice": ["Сузьте сегмент", "Выберите метрику успеха"],
        }

    def evaluate_case_solution(self, case_data, solution_text, history):
        return {
            "summary": f"Оценка кейса {case_data['title']}",
            "score": 81,
            "criteria_scores": [
                {"name": "problem_clarity", "score": 82, "rationale": "Есть структура"},
                {"name": "market_business_logic", "score": 80, "rationale": "Есть бизнес-логика"},
                {"name": "feasibility", "score": 79, "rationale": "Реализуемо"},
                {"name": "differentiation", "score": 83, "rationale": "Есть новая идея"},
            ],
            "strengths": ["Есть структура"],
            "weaknesses": ["Не хватает цифр"],
            "improvements": ["Добавить метрики"],
            "novel_ideas": ["Нестандартный канал"],
        }

    def answer_case_followup(self, case_data, question, history, evaluation=None):
        return {
            "reply": f"Follow-up по кейсу: {question}",
            "risks": ["Слишком общий план"],
            "next_questions": ["Какая одна метрика важнее всего?"],
            "advice": ["Уточните первый эксперимент"],
        }


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    project_data = Path(__file__).resolve().parents[1] / "data"
    temp_data = tmp_path / "data"
    shutil.copytree(project_data, temp_data)
    repository = JsonRepository(temp_data)
    app = create_app(repository=repository, ai_service=FakeAIService())
    return TestClient(app)


def test_health_and_openapi(client: TestClient) -> None:
    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["llm_mode"] == "mock"

    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200
    assert openapi_response.json()["info"]["title"] == "AI Business Trainer MVP"


def test_cases_list_and_detail(client: TestClient) -> None:
    list_response = client.get("/api/v1/cases")
    assert list_response.status_code == 200
    cases = list_response.json()
    assert len(cases) >= 5

    detail_response = client.get(f"/api/v1/cases/{cases[0]['id']}")
    assert detail_response.status_code == 200
    assert "reference_solution_summary" in detail_response.json()


def test_idea_session_flow(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/idea-sessions",
        json={
            "client_id": "demo-user",
            "idea_text": "AI-платформа для развития бизнес-навыков студентов",
            "context": "Интеграция с бизнес-клубом университета",
        },
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["session_id"]
    assert payload["risks"]

    message_response = client.post(
        f"/api/v1/idea-sessions/{payload['session_id']}/messages",
        json={"client_id": "demo-user", "message": "Хочу сфокусироваться на первокурсниках"},
    )
    assert message_response.status_code == 200
    assert message_response.json()["reply"].startswith("Разбор идеи:")


def test_case_session_submit_followup_and_stats(client: TestClient) -> None:
    cases = client.get("/api/v1/cases").json()
    case_id = cases[0]["id"]

    create_response = client.post(
        "/api/v1/case-sessions",
        json={"client_id": "demo-user", "case_id": case_id},
    )
    assert create_response.status_code == 201
    session_id = create_response.json()["session_id"]

    submit_response = client.post(
        f"/api/v1/case-sessions/{session_id}/submit",
        json={
            "client_id": "demo-user",
            "solution_text": "Сужаем сегмент, сокращаем онбординг и считаем time-to-value.",
        },
    )
    assert submit_response.status_code == 200
    submit_payload = submit_response.json()
    assert submit_payload["score"] == 81
    assert submit_payload["criteria_scores"]

    followup_response = client.post(
        f"/api/v1/case-sessions/{session_id}/messages",
        json={"client_id": "demo-user", "message": "Какой эксперимент лучше начать первым?"},
    )
    assert followup_response.status_code == 200
    assert "Follow-up" in followup_response.json()["reply"]

    complete_response = client.post(
        "/api/v1/progress/complete",
        json={
            "client_id": "demo-user",
            "task_type": "case_submission",
            "task_id": session_id,
            "self_marked_complete": True,
        },
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["stats"]["completed_count"] == 1

    stats_response = client.get("/api/v1/stats/demo-user")
    assert stats_response.status_code == 200
    stats_payload = stats_response.json()
    assert stats_payload["sessions_count"] == 1
    assert stats_payload["average_score"] == 81.0


def test_wrong_client_gets_403(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/idea-sessions",
        json={"client_id": "owner", "idea_text": "Платформа для кейс-чемпионатов"},
    )
    session_id = create_response.json()["session_id"]

    response = client.post(
        f"/api/v1/idea-sessions/{session_id}/messages",
        json={"client_id": "intruder", "message": "Попробую залезть в чужую сессию"},
    )
    assert response.status_code == 403


def test_missing_ids_and_corrupted_state_are_handled(client: TestClient) -> None:
    repository = client.app.state.repository
    assert client.get("/api/v1/cases/unknown-case").status_code == 404
    assert client.post(
        "/api/v1/idea-sessions/unknown-session/messages",
        json={"client_id": "demo", "message": "hello"},
    ).status_code == 404

    sessions_path = repository.state_dir / "sessions.json"
    progress_path = repository.state_dir / "progress.json"
    sessions_path.write_text("{broken", encoding="utf-8")
    progress_path.write_text("", encoding="utf-8")

    stats_response = client.get("/api/v1/stats/demo-user")
    assert stats_response.status_code == 200
    assert stats_response.json()["completed_count"] == 0

    create_response = client.post(
        "/api/v1/idea-sessions",
        json={"client_id": "demo-user", "idea_text": "Новая идея после повреждения state"},
    )
    assert create_response.status_code == 201


def test_validation_errors(client: TestClient) -> None:
    response = client.post(
        "/api/v1/idea-sessions",
        json={"client_id": "demo-user", "idea_text": "   "},
    )
    assert response.status_code == 422
