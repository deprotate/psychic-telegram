# Frontend Guide for `/test` API

Для `/test` фронту нужен максимально простой сценарий:

- нет `client_id`
- нет `session_id`
- нет multi-session логики
- сервер держит одну активную test-сессию кейса в памяти
- прогресс solved/unsolved тоже живёт только в памяти процесса

## Base URL

- Local: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

## Как работает flow

1. Фронт запрашивает `GET /test/health`
2. Фронт запрашивает `GET /test/case/state`
3. Фронт запрашивает `GET /test/cases`
4. Пользователь выбирает кейс, фронт вызывает `POST /test/case/start`
5. Пользователь отправляет решение, фронт вызывает `POST /test/case/submit`
6. После `submit` кейс автоматически попадает в solved
7. Если пользователь хочет явно отметить кейс как solved или вернуть его в unsolved, фронт использует progress-endpoint’ы
8. Если пользователь хочет уточнить решение, фронт вызывает `POST /test/case/followup`
9. Для экрана прогресса фронт использует `GET /test/cases/progress`

## Важно

- В `/test` в любой момент времени только один активный кейс
- Новый `POST /test/case/start` сбрасывает только активную test-сессию
- Новый `POST /test/case/start` не сбрасывает solved-progress
- Solved-progress пропадает после рестарта backend
- `POST /test/case/submit` автоматически добавляет активный кейс в solved

## Endpoints

### `GET /test/health`

Проверка режима работы API.

Пример:

```json
{
  "status": "ok",
  "mode": "mock",
  "ready": true,
  "error": null,
  "cases_count": 5
}
```

Поля:

- `mode`: `"mock"` или `"yandex"`
- `ready`: backend готов принимать реальные запросы
- `status`: `"ok"` или `"misconfigured"`

Если `TEST_USE_MOCK=false`, но Yandex неправильно настроен:

```json
{
  "status": "misconfigured",
  "mode": "yandex",
  "ready": false,
  "error": "YANDEX_API_KEY and YANDEX_FOLDER_ID are required when TEST_USE_MOCK=false",
  "cases_count": 5
}
```

### `GET /test/cases`

Список всех кейсов для каталога.

Пример:

```json
[
  {
    "id": "mentor-matching-platform",
    "title": "Платформа персонального менторства от выпускников",
    "theme": "careertech",
    "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
    "difficulty": "medium",
    "tags": ["карьера", "менторство", "выпускники"]
  }
]
```

### `GET /test/cases/{case_id}`

Полное описание одного кейса.

Пример:

```json
{
  "id": "mentor-matching-platform",
  "title": "Платформа персонального менторства от выпускников",
  "theme": "careertech",
  "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
  "difficulty": "medium",
  "tags": ["карьера", "менторство", "выпускники"],
  "background": "У университета огромная база успешных выпускников...",
  "task": "Предложите MVP продукта...",
  "reference_solution_summary": "Сделать умный матчмейкинг...",
  "evaluation_criteria": [
    "problem_clarity",
    "market_business_logic",
    "feasibility",
    "differentiation"
  ]
}
```

### `GET /test/cases/progress`

Возвращает solved/unsolved progress.

Пример:

```json
{
  "solved_cases": [
    {
      "id": "mentor-matching-platform",
      "title": "Платформа персонального менторства от выпускников",
      "theme": "careertech",
      "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
      "difficulty": "medium",
      "tags": ["карьера", "менторство", "выпускники"]
    }
  ],
  "unsolved_cases": [
    {
      "id": "abiturient-journey",
      "title": "ИИ-помощник по выбору образовательной траектории для абитуриентов",
      "theme": "admission",
      "short_description": "Сократить количество отказов от поступления...",
      "difficulty": "hard",
      "tags": ["абитуриенты", "поступление", "ai"]
    }
  ],
  "solved_count": 1,
  "unsolved_count": 2
}
```

### `POST /test/cases/progress/mark-solved`

Явно помечает кейс как solved.

Request:

```json
{
  "case_id": "mentor-matching-platform"
}
```

Response:

```json
{
  "status": "ok",
  "solved_cases": [
    {
      "id": "mentor-matching-platform",
      "title": "Платформа персонального менторства от выпускников",
      "theme": "careertech",
      "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
      "difficulty": "medium",
      "tags": ["карьера", "менторство", "выпускники"]
    }
  ],
  "unsolved_cases": [],
  "solved_count": 1,
  "unsolved_count": 0
}
```

### `POST /test/cases/progress/unmark-solved`

Убирает кейс из solved.

Request:

```json
{
  "case_id": "mentor-matching-platform"
}
```

Response shape такая же, как у `mark-solved`.

### `POST /test/cases/progress/reset`

Полностью очищает solved-progress.

Request body не нужен.

Response:

```json
{
  "status": "ok",
  "solved_cases": [],
  "unsolved_cases": [
    {
      "id": "mentor-matching-platform",
      "title": "Платформа персонального менторства от выпускников",
      "theme": "careertech",
      "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
      "difficulty": "medium",
      "tags": ["карьера", "менторство", "выпускники"]
    }
  ],
  "solved_count": 0,
  "unsolved_count": 1
}
```

### `POST /test/case/start`

Выбирает активный кейс и сбрасывает текущую test-сессию.

Request:

```json
{
  "case_id": "mentor-matching-platform"
}
```

Response:

```json
{
  "mode": "mock",
  "case": {
    "id": "mentor-matching-platform",
    "title": "Платформа персонального менторства от выпускников",
    "theme": "careertech",
    "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
    "difficulty": "medium",
    "tags": ["карьера", "менторство", "выпускники"],
    "background": "У университета огромная база успешных выпускников...",
    "task": "Предложите MVP продукта...",
    "reference_solution_summary": "Сделать умный матчмейкинг...",
    "evaluation_criteria": [
      "problem_clarity",
      "market_business_logic",
      "feasibility",
      "differentiation"
    ]
  },
  "welcome_message": "Кейс активирован. Пришли решение, и я оценю его...",
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован. Пришли решение, и я оценю его..."
    }
  ]
}
```

### `POST /test/case/submit`

Отправляет решение по текущему активному кейсу и автоматически добавляет его в solved.

Request:

```json
{
  "solution_text": "Сначала делаем короткий мэтчинг по целям студента, потом запускаем шаблон первой встречи и считаем NPS."
}
```

Response:

```json
{
  "mode": "mock",
  "case": {
    "id": "mentor-matching-platform",
    "title": "Платформа персонального менторства от выпускников",
    "theme": "careertech",
    "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
    "difficulty": "medium",
    "tags": ["карьера", "менторство", "выпускники"],
    "background": "У университета огромная база успешных выпускников...",
    "task": "Предложите MVP продукта...",
    "reference_solution_summary": "Сделать умный матчмейкинг...",
    "evaluation_criteria": [
      "problem_clarity",
      "market_business_logic",
      "feasibility",
      "differentiation"
    ]
  },
  "summary": "Решение по кейсу выглядит рабочим...",
  "score": 78,
  "criteria_scores": [
    {
      "name": "problem_clarity",
      "score": 80,
      "rationale": "Есть ли ясная постановка задачи."
    }
  ],
  "strengths": ["Ответ структурирован..."],
  "weaknesses": ["Недостаёт более чётких метрик..."],
  "improvements": ["Добавьте 2-3 метрики..."],
  "novel_ideas": ["В решении есть свои идеи..."],
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован..."
    },
    {
      "role": "user",
      "content": "Сначала делаем короткий мэтчинг..."
    },
    {
      "role": "assistant",
      "content": "Решение по кейсу выглядит рабочим..."
    }
  ]
}
```

### `POST /test/case/followup`

Уточняющий вопрос после `submit`.

Request:

```json
{
  "message": "Какой первый эксперимент лучше сделать?"
}
```

Response:

```json
{
  "mode": "mock",
  "case": {
    "id": "mentor-matching-platform",
    "title": "Платформа персонального менторства от выпускников",
    "theme": "careertech",
    "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
    "difficulty": "medium",
    "tags": ["карьера", "менторство", "выпускники"],
    "background": "У университета огромная база успешных выпускников...",
    "task": "Предложите MVP продукта...",
    "reference_solution_summary": "Сделать умный матчмейкинг...",
    "evaluation_criteria": [
      "problem_clarity",
      "market_business_logic",
      "feasibility",
      "differentiation"
    ]
  },
  "reply": "Я бы сфокусировался на одном эксперименте...",
  "risks": ["Ответ может остаться слишком общим..."],
  "next_questions": ["Какая метрика честно покажет, что гипотеза не работает?"],
  "advice": ["Опиши эксперимент в формате гипотеза -> действие -> метрика -> срок."],
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован..."
    },
    {
      "role": "user",
      "content": "Сначала делаем короткий мэтчинг..."
    },
    {
      "role": "assistant",
      "content": "Решение по кейсу выглядит рабочим..."
    },
    {
      "role": "user",
      "content": "Какой первый эксперимент лучше сделать?"
    },
    {
      "role": "assistant",
      "content": "Я бы сфокусировался на одном эксперименте..."
    }
  ]
}
```

### `GET /test/case/state`

Возвращает текущее состояние активной test-сессии.

Если кейс ещё не стартовал:

```json
{
  "mode": "mock",
  "active_case": null,
  "messages": [],
  "last_evaluation": null
}
```

Если кейс уже активен:

```json
{
  "mode": "mock",
  "active_case": {
    "id": "mentor-matching-platform",
    "title": "Платформа персонального менторства от выпускников",
    "theme": "careertech",
    "short_description": "Нужно помочь студентам быстро находить выпускников-менторов...",
    "difficulty": "medium",
    "tags": ["карьера", "менторство", "выпускники"],
    "background": "У университета огромная база успешных выпускников...",
    "task": "Предложите MVP продукта...",
    "reference_solution_summary": "Сделать умный матчмейкинг...",
    "evaluation_criteria": [
      "problem_clarity",
      "market_business_logic",
      "feasibility",
      "differentiation"
    ]
  },
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован..."
    }
  ],
  "last_evaluation": null
}
```

## Ошибки

- `404` если кейс не найден
- `400` если вызвать `submit` без `start`
- `400` если вызвать `followup` до `submit`
- `404` если `mark-solved` или `unmark-solved` получили несуществующий `case_id`
- `503` если выбран Yandex-режим, но backend misconfigured
- `502` если Yandex API упал во время запроса

## Что хранить на фронте

Минимум:

- `cases`
- `solvedCases`
- `unsolvedCases`
- `activeCase`
- `messages`
- `lastEvaluation`
- `mode`
- `loading`
- `error`

Пример типов:

```ts
type CaseSummary = {
  id: string;
  title: string;
  theme: string;
  short_description: string;
  difficulty: string;
  tags: string[];
};

type CaseDetail = CaseSummary & {
  background: string;
  task: string;
  reference_solution_summary: string;
  evaluation_criteria: string[];
};

type TestMessage = {
  role: "user" | "assistant";
  content: string;
};

type TestEvaluation = {
  mode: "mock" | "yandex";
  case: CaseDetail;
  summary: string;
  score: number;
  criteria_scores: Array<{
    name: string;
    score: number;
    rationale?: string | null;
  }>;
  strengths: string[];
  weaknesses: string[];
  improvements: string[];
  novel_ideas: string[];
  messages: TestMessage[];
};

type TestProgress = {
  solved_cases: CaseSummary[];
  unsolved_cases: CaseSummary[];
  solved_count: number;
  unsolved_count: number;
};

type TestState = {
  mode: "mock" | "yandex" | null;
  activeCase: CaseDetail | null;
  messages: TestMessage[];
  lastEvaluation: TestEvaluation | null;
  progress: TestProgress | null;
};
```

## Рекомендуемый frontend flow

- На загрузке страницы:
  - `GET /test/health`
  - `GET /test/case/state`
  - `GET /test/cases/progress`
  - `GET /test/cases`
- При выборе кейса:
  - `POST /test/case/start`
  - обновить `activeCase`, `messages`, `lastEvaluation = null`
- При отправке решения:
  - `POST /test/case/submit`
  - обновить `messages` и `lastEvaluation`
  - затем обновить `GET /test/cases/progress`, если экран прогресса уже показан отдельно
- При follow-up:
  - `POST /test/case/followup`
  - обновить `messages`
- При ручной отметке solved:
  - `POST /test/cases/progress/mark-solved`
- При снятии solved:
  - `POST /test/cases/progress/unmark-solved`
- При полном сбросе:
  - `POST /test/cases/progress/reset`

## Ready-to-use fetch helper

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

## Примеры вызовов

Получить кейсы:

```ts
const cases = await api<CaseSummary[]>("/test/cases");
```

Получить progress:

```ts
const progress = await api<TestProgress>("/test/cases/progress");
```

Старт кейса:

```ts
const started = await api("/test/case/start", {
  method: "POST",
  body: JSON.stringify({
    case_id: "mentor-matching-platform"
  })
});
```

Отправить решение:

```ts
const evaluation = await api("/test/case/submit", {
  method: "POST",
  body: JSON.stringify({
    solution_text: userSolution
  })
});
```

Follow-up:

```ts
const followup = await api("/test/case/followup", {
  method: "POST",
  body: JSON.stringify({
    message: userQuestion
  })
});
```

Явно пометить solved:

```ts
const progress = await api("/test/cases/progress/mark-solved", {
  method: "POST",
  body: JSON.stringify({
    case_id: "mentor-matching-platform"
  })
});
```

Снять solved:

```ts
const progress = await api("/test/cases/progress/unmark-solved", {
  method: "POST",
  body: JSON.stringify({
    case_id: "mentor-matching-platform"
  })
});
```

Сбросить progress:

```ts
const progress = await api("/test/cases/progress/reset", {
  method: "POST"
});
```

Восстановить активную сессию:

```ts
const state = await api("/test/case/state");
```
