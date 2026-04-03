from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main2 import create_main2_app
from services import JsonRepository


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    project_data = Path(__file__).resolve().parents[1] / "data"
    temp_data = tmp_path / "data"
    shutil.copytree(project_data, temp_data)
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    repository = JsonRepository(temp_data)
    app = create_main2_app(repository=repository)
    return TestClient(app)


def test_health_and_openapi(client: TestClient) -> None:
    response = client.get("/test/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "mock"
    assert payload["ready"] is True

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/test/case/start" in paths
    assert "/test/cases/progress" in paths
    assert all(path.startswith("/test") for path in paths)


def test_cases_list_and_detail(client: TestClient) -> None:
    cases = client.get("/test/cases")
    assert cases.status_code == 200
    payload = cases.json()
    assert len(payload) >= 5

    progress = client.get("/test/cases/progress")
    assert progress.status_code == 200
    progress_payload = progress.json()
    assert progress_payload["solved_count"] == 0
    assert progress_payload["unsolved_count"] == len(payload)

    detail = client.get(f"/test/cases/{payload[0]['id']}")
    assert detail.status_code == 200
    assert "reference_solution_summary" in detail.json()


def test_start_submit_followup_and_state(client: TestClient) -> None:
    case_id = client.get("/test/cases").json()[0]["id"]

    start = client.post("/test/case/start", json={"case_id": case_id})
    assert start.status_code == 200
    assert start.json()["case"]["id"] == case_id
    assert len(start.json()["messages"]) == 1

    submit = client.post(
        "/test/case/submit",
        json={"solution_text": "Сначала сегментируем пользователей, сокращаем путь до первой ценности и считаем метрики."},
    )
    assert submit.status_code == 200
    submit_payload = submit.json()
    assert submit_payload["mode"] == "mock"
    assert submit_payload["score"] >= 0
    assert submit_payload["criteria_scores"]
    assert len(submit_payload["messages"]) == 3

    progress_after_submit = client.get("/test/cases/progress")
    assert progress_after_submit.status_code == 200
    progress_payload = progress_after_submit.json()
    assert progress_payload["solved_count"] == 1
    assert case_id in [item["id"] for item in progress_payload["solved_cases"]]

    followup = client.post("/test/case/followup", json={"message": "Какой эксперимент лучше сделать первым?"})
    assert followup.status_code == 200
    followup_payload = followup.json()
    assert followup_payload["mode"] == "mock"
    assert followup_payload["reply"]
    assert len(followup_payload["messages"]) == 5

    state = client.get("/test/case/state")
    assert state.status_code == 200
    state_payload = state.json()
    assert state_payload["active_case"]["id"] == case_id
    assert state_payload["last_evaluation"]["score"] == submit_payload["score"]
    assert len(state_payload["messages"]) == 5


def test_start_resets_previous_state(client: TestClient) -> None:
    cases = client.get("/test/cases").json()
    first_case = cases[0]["id"]
    second_case = cases[1]["id"]

    client.post("/test/case/start", json={"case_id": first_case})
    client.post("/test/case/submit", json={"solution_text": "Первое решение с метриками и MVP."})

    reset = client.post("/test/case/start", json={"case_id": second_case})
    assert reset.status_code == 200
    assert reset.json()["case"]["id"] == second_case
    assert len(reset.json()["messages"]) == 1

    state = client.get("/test/case/state").json()
    assert state["active_case"]["id"] == second_case
    assert state["last_evaluation"] is None
    assert len(state["messages"]) == 1

    progress = client.get("/test/cases/progress").json()
    assert first_case in [item["id"] for item in progress["solved_cases"]]


def test_submit_requires_active_case(client: TestClient) -> None:
    response = client.post("/test/case/submit", json={"solution_text": "Попытка без старта"})
    assert response.status_code == 400


def test_followup_requires_submit(client: TestClient) -> None:
    case_id = client.get("/test/cases").json()[0]["id"]
    client.post("/test/case/start", json={"case_id": case_id})
    response = client.post("/test/case/followup", json={"message": "Можно сразу вопрос?"})
    assert response.status_code == 400


def test_unknown_case_returns_404(client: TestClient) -> None:
    response = client.post("/test/case/start", json={"case_id": "missing-case"})
    assert response.status_code == 404

    mark_response = client.post("/test/cases/progress/mark-solved", json={"case_id": "missing-case"})
    assert mark_response.status_code == 404

    unmark_response = client.post("/test/cases/progress/unmark-solved", json={"case_id": "missing-case"})
    assert unmark_response.status_code == 404


def test_mark_unmark_and_reset_progress(client: TestClient) -> None:
    cases = client.get("/test/cases").json()
    first_case = cases[0]["id"]
    second_case = cases[1]["id"]

    marked = client.post("/test/cases/progress/mark-solved", json={"case_id": first_case})
    assert marked.status_code == 200
    marked_payload = marked.json()
    assert marked_payload["solved_count"] == 1
    assert first_case in [item["id"] for item in marked_payload["solved_cases"]]

    marked_again = client.post("/test/cases/progress/mark-solved", json={"case_id": first_case})
    assert marked_again.status_code == 200
    assert marked_again.json()["solved_count"] == 1

    client.post("/test/cases/progress/mark-solved", json={"case_id": second_case})
    unmarked = client.post("/test/cases/progress/unmark-solved", json={"case_id": first_case})
    assert unmarked.status_code == 200
    unmarked_payload = unmarked.json()
    assert first_case not in [item["id"] for item in unmarked_payload["solved_cases"]]
    assert second_case in [item["id"] for item in unmarked_payload["solved_cases"]]

    reset = client.post("/test/cases/progress/reset")
    assert reset.status_code == 200
    reset_payload = reset.json()
    assert reset_payload["solved_count"] == 0
    assert reset_payload["unsolved_count"] == len(cases)


def test_yandex_mode_requires_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_data = Path(__file__).resolve().parents[1] / "data"
    temp_data = tmp_path / "data"
    shutil.copytree(project_data, temp_data)

    monkeypatch.setenv("TEST_USE_MOCK", "false")
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)

    app = create_main2_app(repository=JsonRepository(temp_data))
    client = TestClient(app)

    health = client.get("/test/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["mode"] == "yandex"
    assert payload["ready"] is False
    assert payload["status"] == "misconfigured"

    start = client.post("/test/case/start", json={"case_id": "fintech-onboarding"})
    assert start.status_code == 503
