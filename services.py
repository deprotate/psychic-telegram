from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from openai import OpenAI


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower()))


class JsonRepository:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.state_dir = self.data_dir / "state"
        self._lock = threading.RLock()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_state_file("sessions.json", [])
        self._ensure_state_file("progress.json", {"completions": []})
        self._ensure_state_file("test_case_states.json", {})

    def _ensure_state_file(self, filename: str, default: Any) -> None:
        path = self.state_dir / filename
        if not path.exists():
            path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.exists() or path.stat().st_size == 0:
            return copy.deepcopy(default)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return copy.deepcopy(default)

    def _write_json(self, path: Path, data: Any) -> None:
        with self._lock:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_cases(self) -> list[dict[str, Any]]:
        return self._read_json(self.data_dir / "cases.json", [])

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_cases() if item["id"] == case_id), None)

    def list_risk_patterns(self) -> list[dict[str, Any]]:
        return self._read_json(self.data_dir / "risk_patterns.json", [])

    def list_sessions(self) -> list[dict[str, Any]]:
        return self._read_json(self.state_dir / "sessions.json", [])

    def create_session(self, session: dict[str, Any]) -> dict[str, Any]:
        path = self.state_dir / "sessions.json"
        with self._lock:
            sessions = self._read_json(path, [])
            sessions.append(session)
            self._write_json(path, sessions)
        return session

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return next((item for item in self.list_sessions() if item["id"] == session_id), None)

    def save_session(self, session: dict[str, Any]) -> dict[str, Any]:
        path = self.state_dir / "sessions.json"
        with self._lock:
            sessions = self._read_json(path, [])
            updated = False
            for index, existing in enumerate(sessions):
                if existing["id"] == session["id"]:
                    sessions[index] = session
                    updated = True
                    break
            if not updated:
                sessions.append(session)
            self._write_json(path, sessions)
        return session

    def record_completion(self, completion: dict[str, Any]) -> dict[str, Any]:
        path = self.state_dir / "progress.json"
        with self._lock:
            progress = self._read_json(path, {"completions": []})
            completions = progress.get("completions", [])
            replaced = False
            for index, existing in enumerate(completions):
                same_task = (
                    existing.get("client_id") == completion["client_id"]
                    and existing.get("task_type") == completion["task_type"]
                    and existing.get("task_id") == completion["task_id"]
                )
                if same_task:
                    completions[index] = completion
                    replaced = True
                    break
            if not replaced:
                completions.append(completion)
            progress["completions"] = completions
            self._write_json(path, progress)
        return completion

    def get_test_case_state(self, client_id: str) -> dict[str, Any]:
        states = self._read_json(self.state_dir / "test_case_states.json", {})
        state = states.get(client_id)
        if not isinstance(state, dict):
            return {}
        return state

    def save_test_case_state(self, client_id: str, state: dict[str, Any]) -> dict[str, Any]:
        path = self.state_dir / "test_case_states.json"
        with self._lock:
            states = self._read_json(path, {})
            states[client_id] = state
            self._write_json(path, states)
        return state

    def get_stats(self, client_id: str) -> dict[str, Any]:
        sessions = [item for item in self.list_sessions() if item.get("client_id") == client_id]
        progress = self._read_json(self.state_dir / "progress.json", {"completions": []})
        completions = [item for item in progress.get("completions", []) if item.get("client_id") == client_id]

        scored_sessions = [item.get("last_score") for item in sessions if item.get("last_score") is not None]
        average_score = None
        if scored_sessions:
            average_score = round(sum(scored_sessions) / len(scored_sessions), 2)

        activity_points = [item.get("updated_at") for item in sessions if item.get("updated_at")]
        activity_points.extend(item.get("completed_at") for item in completions if item.get("completed_at"))
        last_activity = max(activity_points) if activity_points else None

        return {
            "client_id": client_id,
            "completed_count": len(completions),
            "sessions_count": len(sessions),
            "average_score": average_score,
            "last_activity": last_activity,
        }


class BusinessTrainerAIService:
    IDEA_SYSTEM_PROMPT = (
        "Ты — строгий, но полезный ИИ-ассистент бизнес-клуба Центрального Университета. "
        "Ты проводишь имитацию питчинга стартап-идей: ищешь риски, задаёшь вопросы, "
        "подсказываешь, как усилить бизнес-логику и проверить гипотезы."
    )
    CASE_SYSTEM_PROMPT = (
        "Ты — экспертный reviewer бизнес-кейсов. "
        "Ты оцениваешь решение по эталону как по ориентиру, а не как по единственному шаблону, "
        "и честно отмечаешь сильные новые идеи пользователя."
    )

    def __init__(
        self,
        api_key: str | None = None,
        folder_id: str | None = None,
        model_name: str = "yandexgpt-5-pro",
    ) -> None:
        self.api_key = api_key or os.getenv("YANDEX_API_KEY")
        self.folder_id = folder_id or os.getenv("YANDEX_FOLDER_ID")
        self.model_name = model_name
        self.mode = "heuristic"
        self.client: OpenAI | None = None

        if self.api_key and self.folder_id:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://ai.api.cloud.yandex.net/v1",
            )
            self.mode = "yandex"

    def generate_idea_feedback(
        self,
        idea_text: str,
        context: str | None,
        history: list[dict[str, str]],
        references: list[dict[str, Any]],
    ) -> dict[str, Any]:
        fallback = self._fallback_idea_feedback(idea_text=idea_text, context=context, references=references)
        if not self.client:
            return fallback

        payload = {
            "idea_text": idea_text,
            "context": context,
            "relevant_references": references,
            "conversation_history": history,
            "output_schema": {
                "reply": "string",
                "risks": ["string"],
                "next_questions": ["string"],
                "advice": ["string"],
            },
        }
        return self._normalize_idea_feedback(
            self._chat_json(self.IDEA_SYSTEM_PROMPT, payload, fallback),
            fallback,
        )

    def evaluate_case_solution(
        self,
        case_data: dict[str, Any],
        solution_text: str,
        history: list[dict[str, str]],
    ) -> dict[str, Any]:
        fallback = self._fallback_case_evaluation(case_data=case_data, solution_text=solution_text)
        if not self.client:
            return fallback

        payload = {
            "case": case_data,
            "user_solution": solution_text,
            "conversation_history": history,
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
        return self._normalize_case_evaluation(
            self._chat_json(self.CASE_SYSTEM_PROMPT, payload, fallback),
            fallback,
        )

    def answer_case_followup(
        self,
        case_data: dict[str, Any],
        question: str,
        history: list[dict[str, str]],
        evaluation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = self._fallback_case_followup(case_data=case_data, question=question, evaluation=evaluation)
        if not self.client:
            return fallback

        payload = {
            "case": case_data,
            "question": question,
            "last_evaluation": evaluation,
            "conversation_history": history,
            "output_schema": {
                "reply": "string",
                "next_questions": ["string"],
                "risks": ["string"],
                "advice": ["string"],
            },
        }
        return self._normalize_idea_feedback(
            self._chat_json(self.CASE_SYSTEM_PROMPT, payload, fallback),
            fallback,
        )

    def _chat_json(self, system_prompt: str, user_payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        assert self.client is not None
        try:
            response = self.client.chat.completions.create(
                model=f"gpt://{self.folder_id}/{self.model_name}",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            "Ответь строго валидным JSON без markdown и без пояснений. "
                            f"Данные:\n{json.dumps(user_payload, ensure_ascii=False)}"
                        ),
                    },
                ],
                temperature=0.5,
                max_tokens=1800,
            )
            content = response.choices[0].message.content or ""
            return self._extract_json(content) or fallback
        except Exception:
            return fallback

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

    def _normalize_idea_feedback(self, payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        return {
            "reply": str(payload.get("reply") or fallback["reply"]),
            "risks": self._normalize_string_list(payload.get("risks"), fallback["risks"]),
            "next_questions": self._normalize_string_list(payload.get("next_questions"), fallback["next_questions"]),
            "advice": self._normalize_string_list(payload.get("advice"), fallback["advice"]),
        }

    def _normalize_case_evaluation(self, payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        raw_criteria = payload.get("criteria_scores")
        criteria_scores = fallback["criteria_scores"]
        if isinstance(raw_criteria, dict):
            criteria_scores = [
                {"name": key, "score": max(0, min(100, int(value))), "rationale": None}
                for key, value in raw_criteria.items()
            ]
        elif isinstance(raw_criteria, list) and raw_criteria:
            criteria_scores = []
            for item in raw_criteria:
                if not isinstance(item, dict):
                    continue
                try:
                    score = int(item.get("score", 0))
                except (TypeError, ValueError):
                    score = 0
                criteria_scores.append(
                    {
                        "name": str(item.get("name") or "criterion"),
                        "score": max(0, min(100, score)),
                        "rationale": item.get("rationale"),
                    }
                )
            if not criteria_scores:
                criteria_scores = fallback["criteria_scores"]

        score = payload.get("score", fallback["score"])
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = fallback["score"]

        return {
            "summary": str(payload.get("summary") or fallback["summary"]),
            "score": max(0, min(100, score)),
            "criteria_scores": criteria_scores,
            "strengths": self._normalize_string_list(payload.get("strengths"), fallback["strengths"]),
            "weaknesses": self._normalize_string_list(payload.get("weaknesses"), fallback["weaknesses"]),
            "improvements": self._normalize_string_list(payload.get("improvements"), fallback["improvements"]),
            "novel_ideas": self._normalize_string_list(payload.get("novel_ideas"), fallback["novel_ideas"]),
        }

    def _normalize_string_list(self, value: Any, fallback: list[str]) -> list[str]:
        if not isinstance(value, list):
            return fallback
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned or fallback

    def _fallback_idea_feedback(
        self,
        idea_text: str,
        context: str | None,
        references: list[dict[str, Any]],
    ) -> dict[str, Any]:
        risks: list[str] = []
        next_questions: list[str] = []
        advice: list[str] = []

        for ref in references[:3]:
            risks.append(f"{ref['title']}: {ref['reason']}")
            questions = ref.get("questions") or []
            if questions:
                next_questions.append(questions[0])
            description = ref.get("description")
            if description:
                advice.append(description)

        if not risks:
            risks = [
                "Пока не видно подтверждённой боли клиента и способа быстро проверить спрос.",
                "Не зафиксирована unit-экономика и ограничения запуска.",
                "Нет ясного отличия от существующих решений на рынке.",
            ]
        if not next_questions:
            next_questions = [
                "Какой самый узкий сегмент пользователей вы берёте первым и почему именно он?",
                "Какая метрика покажет через 2-4 недели, что идея реально цепляет рынок?",
                "Что в модели может сломаться первым: привлечение, экономика или операционка?",
            ]
        if not advice:
            advice = [
                "Сформулируйте одну главную проблему пользователя и свяжите каждую фичу с её решением.",
                "Подготовьте быстрый способ валидировать спрос до серьёзных вложений.",
                "Разложите запуск на гипотезы: спрос, канал, операционная реализация и экономика.",
            ]

        reply_parts = [
            "Идея выглядит как хороший старт для тренировки питчинга, но пока ей нужно больше конкретики.",
            f"Я бы в первую очередь проверил: {risks[0].lower()}",
        ]
        if context:
            reply_parts.append("Дополнительный контекст полезен, но его стоит перевести в проверяемые гипотезы.")

        return {
            "reply": " ".join(reply_parts),
            "risks": risks[:5],
            "next_questions": next_questions[:3],
            "advice": advice[:3],
        }

    def _fallback_case_evaluation(self, case_data: dict[str, Any], solution_text: str) -> dict[str, Any]:
        reference_tokens = tokenize(case_data.get("reference_solution_summary", ""))
        solution_tokens = tokenize(solution_text)
        overlap = len(reference_tokens & solution_tokens)
        novelty_tokens = solution_tokens - reference_tokens

        score = min(96, 55 + overlap * 3)
        if len(solution_text.split()) < 40:
            score = max(35, score - 12)

        criteria = [
            {
                "name": "problem_clarity",
                "score": max(40, min(95, score)),
                "rationale": "Проверяем, насколько чётко сформулирована проблема и цель решения.",
            },
            {
                "name": "market_business_logic",
                "score": max(35, min(95, score - 3)),
                "rationale": "Смотрим на бизнес-механику, сегмент и аргументацию по модели.",
            },
            {
                "name": "feasibility",
                "score": max(35, min(95, score - 5)),
                "rationale": "Оцениваем реализуемость и реалистичность первого шага.",
            },
            {
                "name": "differentiation",
                "score": max(35, min(95, score + 2)),
                "rationale": "Отмечаем, есть ли внятное отличие и новая идея.",
            },
        ]

        novel_ideas = []
        if novelty_tokens:
            novel_ideas.append(
                "Есть новые элементы по сравнению с эталоном; их стоит сохранить, если сможете доказать реалистичность."
            )

        return {
            "summary": (
                f"Решение по кейсу «{case_data.get('title', 'Без названия')}» выглядит жизнеспособным, "
                "но ему не хватает более чёткой приоритизации гипотез и доказательства реализуемости."
            ),
            "score": score,
            "criteria_scores": criteria,
            "strengths": [
                "В решении есть понятная попытка структурировать ответ под бизнес-задачу.",
                "Прослеживается фокус на практическом шаге, а не только на абстрактной стратегии.",
            ],
            "weaknesses": [
                "Не хватает более явной привязки к цифрам, ограничениям и проверяемым метрикам.",
                "Есть риск, что часть гипотез не валидируется на раннем этапе достаточно дешёво.",
            ],
            "improvements": [
                "Добавьте 2-3 метрики успеха и срок проверки гипотез.",
                "Разделите решение на быстрый MVP-этап и масштабирование.",
                "Явно покажите, почему выбранный подход сильнее альтернатив.",
            ],
            "novel_ideas": novel_ideas,
        }

    def _fallback_case_followup(
        self,
        case_data: dict[str, Any],
        question: str,
        evaluation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        score = evaluation.get("score") if evaluation else None
        reply = (
            f"По кейсу «{case_data.get('title', 'Без названия')}» я бы усилил ответ через одну конкретную проверку: "
            "сначала зафиксируйте гипотезу, потом метрику, потом самый дешёвый эксперимент."
        )
        if score is not None:
            reply += f" Сейчас решение тянет примерно на {score}/100, и основной рост даст больше конкретики по реализации."

        return {
            "reply": reply,
            "risks": [
                "Слишком общий ответ без чёткой последовательности шагов.",
                "Недостаточно аргументов, почему выбранный путь сработает лучше альтернатив.",
            ],
            "next_questions": [
                f"Какой один эксперимент лучше всего отвечает на ваш вопрос: {question}",
                "Какая метрика провалит гипотезу максимально быстро и честно?",
            ],
            "advice": [
                "Опирайтесь на ограничения кейса и явно ссылайтесь на них в ответе.",
                "Разведите стратегическую идею и первый практический шаг, чтобы решение было убедительнее.",
            ],
        }


def build_reference_items(
    idea_text: str,
    risk_patterns: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    top_k: int = 3,
) -> list[dict[str, Any]]:
    text_tokens = tokenize(idea_text)
    scored_items: list[tuple[int, dict[str, Any]]] = []

    for item in risk_patterns:
        item_tokens = tokenize(" ".join(item.get("tags", [])) + " " + item.get("title", ""))
        overlap = len(text_tokens & item_tokens)
        if overlap:
            scored_items.append(
                (
                    overlap + 3,
                    {
                        **item,
                        "source_type": "risk_pattern",
                        "reason": item.get("description", "Подходит по тематике и рискам запуска."),
                    },
                )
            )

    for item in cases:
        item_tokens = tokenize(" ".join(item.get("tags", [])) + " " + item.get("theme", ""))
        overlap = len(text_tokens & item_tokens)
        if overlap:
            scored_items.append(
                (
                    overlap + 1,
                    {
                        "id": item["id"],
                        "title": item["title"],
                        "source_type": "business_case",
                        "reason": f"Похожий бизнес-контекст: {item.get('short_description', '')}",
                        "questions": [],
                        "description": item.get("reference_solution_summary", ""),
                    },
                )
            )

    scored_items.sort(key=lambda pair: pair[0], reverse=True)
    references = [item for _, item in scored_items[:top_k]]
    if references:
        return references

    return [
        {
            "id": "generic-market-validation",
            "title": "Ранняя проверка спроса",
            "source_type": "risk_pattern",
            "reason": "Для любой идеи важно быстро проверить реальность спроса и economics.",
            "questions": [
                "Какой самый быстрый способ проверить, что пользователи готовы менять своё поведение?",
            ],
            "description": "Соберите короткий тест спроса до масштабирования.",
        }
    ]


def build_case_reference(case_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": case_data["id"],
            "title": case_data["title"],
            "source_type": "business_case",
            "reason": "Оценка строится на условиях кейса и эталонном направлении решения.",
        }
    ]


def create_session_record(
    *,
    client_id: str,
    mode: str,
    title: str,
    idea_text: str | None = None,
    case_id: str | None = None,
    context: str | None = None,
    used_references: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    timestamp = utc_now_iso()
    return {
        "id": str(uuid4()),
        "client_id": client_id,
        "mode": mode,
        "title": title,
        "idea_text": idea_text,
        "case_id": case_id,
        "context": context,
        "used_references": used_references or [],
        "messages": [],
        "status": "active",
        "last_score": None,
        "last_evaluation": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def append_session_message(session: dict[str, Any], role: str, content: str) -> dict[str, Any]:
    session.setdefault("messages", []).append({"role": role, "content": content, "timestamp": utc_now_iso()})
    session["updated_at"] = utc_now_iso()
    return session
