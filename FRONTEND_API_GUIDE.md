# Frontend Guide for AI Business Trainer API

## 1. Base URL and General Rules

- Base URL for local dev: `http://localhost:8000`
- Swagger / manual check: `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`
- Auth in MVP does not exist.
- Frontend must generate and keep a stable `client_id` on the client side.
- Simplest approach: save `client_id` once in `localStorage`.

Example `client_id`:

```ts
const clientId =
  localStorage.getItem("client_id") ??
  crypto.randomUUID();

localStorage.setItem("client_id", clientId);
```

Important:

- Every request that creates or continues user work must send the same `client_id`.
- `session_id` is returned by backend after session creation and must be stored on the frontend.
- If you send another `client_id` for an existing session, backend returns `403`.

## 2. Main User Flows

### Flow A. Startup Idea Mode

1. User enters startup idea and optional context.
2. Frontend calls `POST /api/v1/idea-sessions`.
3. Backend returns:
   - `session_id`
   - first AI answer
   - risks
   - next questions
   - advice
   - used references
4. Frontend stores `session_id` and renders chat thread.
5. On each next user message, frontend calls `POST /api/v1/idea-sessions/{session_id}/messages`.
6. When user decides task is finished, frontend optionally calls `POST /api/v1/progress/complete`.

### Flow B. Business Case Mode

1. Frontend loads cases through `GET /api/v1/cases`.
2. User picks one case.
3. Frontend can optionally load full case through `GET /api/v1/cases/{case_id}`.
4. Frontend creates work session through `POST /api/v1/case-sessions`.
5. User writes solution.
6. Frontend sends solution to `POST /api/v1/case-sessions/{session_id}/submit`.
7. Backend returns structured evaluation with `score`, strengths, weaknesses, improvements and criterion scores.
8. For clarifying questions after evaluation, frontend calls `POST /api/v1/case-sessions/{session_id}/messages`.
9. When user finishes, frontend optionally calls `POST /api/v1/progress/complete`.
10. Frontend loads user stats with `GET /api/v1/stats/{client_id}`.

## 3. Endpoints

### `GET /health`

Use for simple app availability check.

Response example:

```json
{
  "status": "ok",
  "llm_mode": "yandex",
  "cases_count": 5,
  "risk_patterns_count": 12
}
```

### `GET /api/v1/cases`

Returns short cards for cases list page.

Response example:

```json
[
  {
    "id": "fintech-onboarding",
    "title": "Ускорение онбординга в студенческом финтехе",
    "theme": "fintech",
    "short_description": "Нужно увеличить конверсию студентов...",
    "difficulty": "medium",
    "tags": ["финтех", "студенты", "онбординг"]
  }
]
```

### `GET /api/v1/cases/{case_id}`

Returns full case for case page or modal.

Response example:

```json
{
  "id": "fintech-onboarding",
  "title": "Ускорение онбординга в студенческом финтехе",
  "theme": "fintech",
  "short_description": "Нужно увеличить конверсию студентов...",
  "difficulty": "medium",
  "tags": ["финтех", "студенты", "онбординг"],
  "background": "Студенческий финтех-сервис...",
  "task": "Предложите MVP-решение...",
  "reference_solution_summary": "Разбить онбординг на сегменты...",
  "evaluation_criteria": [
    "problem_clarity",
    "market_business_logic",
    "feasibility",
    "differentiation"
  ]
}
```

### `POST /api/v1/idea-sessions`

Creates idea session and returns first AI response.

Request:

```json
{
  "client_id": "web-demo-user-1",
  "idea_text": "Хочу сделать ИИ-тренажёр для студентов по кейсам и стартап-питчам",
  "context": "Интеграция с бизнес-клубом Центрального Университета"
}
```

Response:

```json
{
  "session_id": "db9f9dcb-4de8-44ca-8b97-f7190dca2d01",
  "reply": "Идея выглядит как хороший старт...",
  "used_references": [
    {
      "id": "market-validation",
      "title": "Недостаточная проверка спроса",
      "source_type": "risk_pattern",
      "reason": "Идея выглядит интересной, но не видно дешёвого..."
    }
  ],
  "next_questions": [
    "Какой эксперимент за 1-2 недели честно покажет наличие спроса?"
  ],
  "risks": [
    "Недостаточная проверка спроса: ..."
  ],
  "advice": [
    "Сформулируйте одну главную проблему пользователя..."
  ]
}
```

### `POST /api/v1/idea-sessions/{session_id}/messages`

Continues idea discussion.

Request:

```json
{
  "client_id": "web-demo-user-1",
  "message": "Хочу сузить сегмент до студентов, которые участвуют в кейс-чемпионатах"
}
```

Response shape is the same as in idea session creation.

### `POST /api/v1/case-sessions`

Creates case-solving session.

Request:

```json
{
  "client_id": "web-demo-user-1",
  "case_id": "fintech-onboarding"
}
```

Response:

```json
{
  "session_id": "4e4668d8-532b-4504-ae48-6149175938db",
  "case": {
    "id": "fintech-onboarding",
    "title": "Ускорение онбординга в студенческом финтехе",
    "theme": "fintech",
    "short_description": "Нужно увеличить конверсию студентов...",
    "difficulty": "medium",
    "tags": ["финтех", "студенты", "онбординг"],
    "background": "Студенческий финтех-сервис...",
    "task": "Предложите MVP-решение...",
    "reference_solution_summary": "Разбить онбординг на сегменты...",
    "evaluation_criteria": [
      "problem_clarity",
      "market_business_logic",
      "feasibility",
      "differentiation"
    ]
  },
  "welcome_message": "Сессия по кейсу создана. Отправьте своё решение..."
}
```

### `POST /api/v1/case-sessions/{session_id}/submit`

Submits user solution for evaluation.

Request:

```json
{
  "client_id": "web-demo-user-1",
  "solution_text": "Сначала сегментируем новых пользователей, сокращаем путь до первой полезной операции..."
}
```

Response:

```json
{
  "session_id": "4e4668d8-532b-4504-ae48-6149175938db",
  "summary": "Решение по кейсу выглядит жизнеспособным...",
  "score": 81,
  "criteria_scores": [
    {
      "name": "problem_clarity",
      "score": 82,
      "rationale": "Есть структура"
    }
  ],
  "strengths": ["Есть структура"],
  "weaknesses": ["Не хватает цифр"],
  "improvements": ["Добавить метрики"],
  "novel_ideas": ["Нестандартный канал"],
  "used_references": [
    {
      "id": "fintech-onboarding",
      "title": "Ускорение онбординга в студенческом финтехе",
      "source_type": "business_case",
      "reason": "Оценка строится на условиях кейса и эталонном направлении решения."
    }
  ]
}
```

### `POST /api/v1/case-sessions/{session_id}/messages`

For follow-up questions after case evaluation.

Request:

```json
{
  "client_id": "web-demo-user-1",
  "message": "Какой эксперимент лучше сделать первым?"
}
```

Response shape:

```json
{
  "session_id": "4e4668d8-532b-4504-ae48-6149175938db",
  "reply": "По кейсу я бы усилил ответ через одну конкретную проверку...",
  "used_references": [
    {
      "id": "fintech-onboarding",
      "title": "Ускорение онбординга в студенческом финтехе",
      "source_type": "business_case",
      "reason": "Оценка строится на условиях кейса и эталонном направлении решения."
    }
  ],
  "next_questions": ["Какая метрика провалит гипотезу быстрее всего?"],
  "risks": ["Слишком общий ответ без чёткой последовательности шагов."],
  "advice": ["Опирайтесь на ограничения кейса и явно ссылайтесь на них."]
}
```

### `POST /api/v1/progress/complete`

Marks task as completed by user.

Request:

```json
{
  "client_id": "web-demo-user-1",
  "task_type": "case_submission",
  "task_id": "4e4668d8-532b-4504-ae48-6149175938db",
  "self_marked_complete": true
}
```

Response:

```json
{
  "status": "ok",
  "completion": {
    "client_id": "web-demo-user-1",
    "task_type": "case_submission",
    "task_id": "4e4668d8-532b-4504-ae48-6149175938db",
    "self_marked_complete": true,
    "completed_at": "2026-04-03T13:10:00+00:00"
  },
  "stats": {
    "client_id": "web-demo-user-1",
    "completed_count": 1,
    "sessions_count": 2,
    "average_score": 81.0,
    "last_activity": "2026-04-03T13:10:00+00:00"
  }
}
```

### `GET /api/v1/stats/{client_id}`

Returns basic user stats.

Response:

```json
{
  "client_id": "web-demo-user-1",
  "completed_count": 1,
  "sessions_count": 2,
  "average_score": 81.0,
  "last_activity": "2026-04-03T13:10:00+00:00"
}
```

## 4. Frontend State You Should Store

Minimum state:

- `client_id`
- current mode: `idea` or `case`
- `selected_case_id`
- `active_session_id`
- messages array for UI
- latest case evaluation
- stats for profile/dashboard

Recommended chat message shape on frontend:

```ts
type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
};
```

Recommended local state per idea session:

```ts
type IdeaSessionState = {
  sessionId: string;
  reply: string;
  risks: string[];
  nextQuestions: string[];
  advice: string[];
  usedReferences: Array<{
    id: string;
    title: string;
    source_type: string;
    reason: string;
  }>;
};
```

Recommended local state per case evaluation:

```ts
type CaseEvaluation = {
  sessionId: string;
  summary: string;
  score: number;
  criteriaScores: Array<{
    name: string;
    score: number;
    rationale?: string | null;
  }>;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
  novelIdeas: string[];
};
```

## 5. Error Handling

Backend can return:

- `404` if `case_id` or `session_id` does not exist
- `403` if `client_id` does not match session owner
- `422` if required fields are empty
- `500` if server-side unexpected error happens

Recommended frontend behavior:

- For `404`: show “сессия не найдена” or recreate session.
- For `403`: clear broken local session and ask user to restart flow.
- For `422`: validate inputs before request and show inline error.
- For `500`: show retry action and keep user text in UI.

## 6. Ready-to-Use Fetch Helpers

```ts
const API_BASE = "http://localhost:8000";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text}`);
  }

  return response.json() as Promise<T>;
}
```

Create idea session:

```ts
const ideaSession = await api("/api/v1/idea-sessions", {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    idea_text: ideaText,
    context
  })
});
```

Continue idea chat:

```ts
const ideaReply = await api(`/api/v1/idea-sessions/${sessionId}/messages`, {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    message
  })
});
```

Create case session:

```ts
const caseSession = await api("/api/v1/case-sessions", {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    case_id: caseId
  })
});
```

Submit case solution:

```ts
const evaluation = await api(`/api/v1/case-sessions/${sessionId}/submit`, {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    solution_text: solutionText
  })
});
```

Load stats:

```ts
const stats = await api(`/api/v1/stats/${clientId}`);
```

## 7. Integration Notes for MVP

- Backend already supports CORS for MVP.
- If frontend runs on another port, backend should still accept it by default.
- For production later, `APP_CORS_ORIGINS` should be narrowed down to explicit domains.
- The API is stateful through `session_id`, but user identity is still fully client-driven through `client_id`.
- Do not generate a new `client_id` on every refresh, иначе пользователь потеряет связность своих сессий и статистики.
