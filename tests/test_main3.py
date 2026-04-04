from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main3 import create_main3_app
from services import JsonRepository


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    project_data = Path(__file__).resolve().parents[1] / "data"
    temp_data = tmp_path / "data"
    shutil.copytree(project_data, temp_data)
    monkeypatch.setenv("TEST_USE_MOCK", "true")
    repository = JsonRepository(temp_data)
    app = create_main3_app(repository=repository)
    return TestClient(app)


def test_health_and_openapi(client: TestClient) -> None:
    response = client.get("/test3/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "mock"
    assert payload["ready"] is True

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/test3/mode" in paths
    assert "/test3/case/start" in paths
    assert "/test3/cases/progress" in paths


def test_start_submit_followup_and_state_are_scoped_by_client(client: TestClient) -> None:
    case_id = client.get("/test3/cases").json()[0]["id"]

    start = client.post("/test3/case/start", json={"client_id": "alice", "case_id": case_id})
    assert start.status_code == 200
    assert start.json()["case"]["id"] == case_id
    assert len(start.json()["messages"]) == 1

    submit = client.post(
        "/test3/case/submit",
        json={
            "client_id": "alice",
            "solution_text": "Сначала сегментируем пользователей, сокращаем путь до первой ценности и считаем метрики.",
        },
    )
    assert submit.status_code == 200
    submit_payload = submit.json()
    assert submit_payload["mode"] == "mock"
    assert submit_payload["criteria_scores"]
    assert len(submit_payload["messages"]) == 3

    followup = client.post(
        "/test3/case/followup",
        json={"client_id": "alice", "message": "Какой эксперимент лучше сделать первым?"},
    )
    assert followup.status_code == 200
    assert len(followup.json()["messages"]) == 5

    state = client.get("/test3/case/state", params={"client_id": "alice"})
    assert state.status_code == 200
    state_payload = state.json()
    assert state_payload["active_case"]["id"] == case_id
    assert state_payload["last_evaluation"]["score"] == submit_payload["score"]
    assert len(state_payload["messages"]) == 5


def test_clients_do_not_see_each_others_active_case_or_progress(client: TestClient) -> None:
    cases = client.get("/test3/cases").json()
    first_case = cases[0]["id"]
    second_case = cases[1]["id"]

    alice_start = client.post("/test3/case/start", json={"client_id": "alice", "case_id": first_case})
    bob_start = client.post("/test3/case/start", json={"client_id": "bob", "case_id": second_case})
    assert alice_start.status_code == 200
    assert bob_start.status_code == 200

    alice_submit = client.post(
        "/test3/case/submit",
        json={"client_id": "alice", "solution_text": "Делаем MVP, считаем первые метрики и валидируем спрос."},
    )
    assert alice_submit.status_code == 200

    alice_state = client.get("/test3/case/state", params={"client_id": "alice"}).json()
    bob_state = client.get("/test3/case/state", params={"client_id": "bob"}).json()
    assert alice_state["active_case"]["id"] == first_case
    assert bob_state["active_case"]["id"] == second_case
    assert alice_state["last_evaluation"] is not None
    assert bob_state["last_evaluation"] is None
    assert len(bob_state["messages"]) == 1

    alice_progress = client.get("/test3/cases/progress", params={"client_id": "alice"}).json()
    bob_progress = client.get("/test3/cases/progress", params={"client_id": "bob"}).json()
    assert first_case in [item["id"] for item in alice_progress["solved_cases"]]
    assert first_case not in [item["id"] for item in bob_progress["solved_cases"]]


def test_start_resets_only_current_clients_session(client: TestClient) -> None:
    cases = client.get("/test3/cases").json()
    first_case = cases[0]["id"]
    second_case = cases[1]["id"]

    client.post("/test3/case/start", json={"client_id": "alice", "case_id": first_case})
    client.post("/test3/case/submit", json={"client_id": "alice", "solution_text": "Первое решение с метриками и MVP."})

    reset = client.post("/test3/case/start", json={"client_id": "alice", "case_id": second_case})
    assert reset.status_code == 200
    assert reset.json()["case"]["id"] == second_case
    assert len(reset.json()["messages"]) == 1

    state = client.get("/test3/case/state", params={"client_id": "alice"}).json()
    assert state["active_case"]["id"] == second_case
    assert state["last_evaluation"] is None
    assert len(state["messages"]) == 1

    progress = client.get("/test3/cases/progress", params={"client_id": "alice"}).json()
    assert first_case in [item["id"] for item in progress["solved_cases"]]


def test_followup_requires_submit_for_that_client(client: TestClient) -> None:
    case_id = client.get("/test3/cases").json()[0]["id"]
    client.post("/test3/case/start", json={"client_id": "alice", "case_id": case_id})
    response = client.post("/test3/case/followup", json={"client_id": "alice", "message": "Можно сразу вопрос?"})
    assert response.status_code == 400


def test_mark_unmark_and_reset_progress_are_client_scoped(client: TestClient) -> None:
    cases = client.get("/test3/cases").json()
    first_case = cases[0]["id"]
    second_case = cases[1]["id"]

    marked = client.post("/test3/cases/progress/mark-solved", json={"client_id": "alice", "case_id": first_case})
    assert marked.status_code == 200
    assert first_case in [item["id"] for item in marked.json()["solved_cases"]]

    client.post("/test3/cases/progress/mark-solved", json={"client_id": "bob", "case_id": second_case})
    unmarked = client.post("/test3/cases/progress/unmark-solved", json={"client_id": "alice", "case_id": first_case})
    assert unmarked.status_code == 200
    assert first_case not in [item["id"] for item in unmarked.json()["solved_cases"]]

    bob_progress = client.get("/test3/cases/progress", params={"client_id": "bob"}).json()
    assert second_case in [item["id"] for item in bob_progress["solved_cases"]]

    reset = client.post("/test3/cases/progress/reset", json={"client_id": "bob"})
    assert reset.status_code == 200
    assert reset.json()["solved_count"] == 0


def test_missing_client_id_or_case_is_rejected(client: TestClient) -> None:
    response = client.get("/test3/case/state")
    assert response.status_code == 422

    unknown = client.post("/test3/case/start", json={"client_id": "alice", "case_id": "missing-case"})
    assert unknown.status_code == 404


def test_corrupted_test_state_file_is_handled(client: TestClient) -> None:
    repository = client.app.state.repository
    state_path = repository.state_dir / "test_case_states.json"
    state_path.write_text("{broken", encoding="utf-8")

    state_response = client.get("/test3/case/state", params={"client_id": "alice"})
    assert state_response.status_code == 200
    assert state_response.json()["active_case"] is None

    create_response = client.post(
        "/test3/case/start",
        json={"client_id": "alice", "case_id": client.get("/test3/cases").json()[0]["id"]},
    )
    assert create_response.status_code == 200


def test_yandex_mode_requires_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_data = Path(__file__).resolve().parents[1] / "data"
    temp_data = tmp_path / "data"
    shutil.copytree(project_data, temp_data)

    monkeypatch.setenv("TEST_USE_MOCK", "false")
    monkeypatch.delenv("YANDEX_API_KEY", raising=False)
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)

    app = create_main3_app(repository=JsonRepository(temp_data))
    client = TestClient(app)

    health = client.get("/test3/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["mode"] == "yandex"
    assert payload["ready"] is False
    assert payload["status"] == "misconfigured"

    start = client.post("/test3/case/start", json={"client_id": "alice", "case_id": "fintech-onboarding"})
    assert start.status_code == 503
