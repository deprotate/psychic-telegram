Для `\test` фронту теперь нужен совсем простой сценарий: никаких `client_id`, `session_id`, multiple sessions и user progress. Сервер держит одну глобальную активную сессию кейса в памяти, а фронт просто работает с текущим состоянием.

**Base URL**
- Локально: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

**Как работает flow**
1. Фронт загружает список кейсов через `GET /test/cases`
2. Пользователь выбирает кейс
3. Фронт вызывает `POST /test/case/start`
4. Пользователь пишет решение
5. Фронт вызывает `POST /test/case/submit`
6. Если пользователь хочет доработать решение, фронт вызывает `POST /test/case/followup`
7. После refresh фронт может восстановить экран через `GET /test/case/state`

**Важно**
- В `\test` нет user identity
- В `\test` нет session id
- В `\test` в каждый момент времени существует только один активный кейс
- Новый `POST /test/case/start` полностью сбрасывает предыдущую test-сессию

**Endpoints**

`GET /test/health`
Проверка режима работы API.

Пример ответа:
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
- `ready`: готов ли backend реально обслуживать запросы
- `status`: `"ok"` или `"misconfigured"`

Если `TEST_USE_MOCK=false`, но нет ключей Яндекса, будет что-то вроде:
```json
{
  "status": "misconfigured",
  "mode": "yandex",
  "ready": false,
  "error": "YANDEX_API_KEY and YANDEX_FOLDER_ID are required when TEST_USE_MOCK=false",
  "cases_count": 5
}
```

`GET /test/cases`
Список кейсов для карточек/каталога.

Пример:
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

`GET /test/cases/{case_id}`
Полное описание кейса.

Пример:
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

`POST /test/case/start`
Выбирает активный кейс и сбрасывает прошлую test-сессию.

Request:
```json
{
  "case_id": "fintech-onboarding"
}
```

Response:
```json
{
  "mode": "mock",
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
  "welcome_message": "Кейс активирован. Пришли решение, и я оценю его...",
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован. Пришли решение, и я оценю его..."
    }
  ]
}
```

`POST /test/case/submit`
Отправка решения по текущему активному кейсу.

Request:
```json
{
  "solution_text": "Сначала сегментируем пользователей, сокращаем путь до первой ценности и считаем метрики."
}
```

Response:
```json
{
  "mode": "mock",
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
      "content": "Сначала сегментируем пользователей..."
    },
    {
      "role": "assistant",
      "content": "Решение по кейсу выглядит рабочим..."
    }
  ]
}
```

`POST /test/case/followup`
Уточняющий вопрос после submit.

Request:
```json
{
  "message": "Какой эксперимент лучше сделать первым?"
}
```

Response:
```json
{
  "mode": "mock",
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
      "content": "Сначала сегментируем пользователей..."
    },
    {
      "role": "assistant",
      "content": "Решение по кейсу выглядит рабочим..."
    },
    {
      "role": "user",
      "content": "Какой эксперимент лучше сделать первым?"
    },
    {
      "role": "assistant",
      "content": "Я бы сфокусировался на одном эксперименте..."
    }
  ]
}
```

`GET /test/case/state`
Получение текущего состояния test-сессии. Это главный endpoint для восстановления UI после refresh.

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
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован..."
    }
  ],
  "last_evaluation": null
}
```

**Ошибки**
- `404` если кейс не найден
- `400` если вызвать `submit` без `start`
- `400` если вызвать `followup` до `submit`
- `503` если выбран Yandex-режим, но backend misconfigured
- `502` если Yandex API реально упал во время запроса

**Что хранить на фронте**
Минимум:
- `cases`
- `activeCase`
- `messages`
- `lastEvaluation`
- `mode`
- `loading`
- `error`

Пример state:
```ts
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

type TestState = {
  mode: "mock" | "yandex" | null;
  activeCase: CaseDetail | null;
  messages: TestMessage[];
  lastEvaluation: TestEvaluation | null;
};
```

**Рекомендуемый frontend flow**
- На загрузке страницы:
  - `GET /test/health`
  - `GET /test/case/state`
  - если кейс не активен, показать список из `GET /test/cases`
- При выборе кейса:
  - `POST /test/case/start`
  - взять `case`, `welcome_message`, `messages`
- При отправке решения:
  - `POST /test/case/submit`
  - обновить `messages` и `lastEvaluation`
- При follow-up:
  - `POST /test/case/followup`
  - обновить `messages`

**Готовый fetch helper**
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

**Примеры вызовов**
Загрузка кейсов:
```ts
const cases = await api("/test/cases");
```

Старт кейса:
```ts
const started = await api("/test/case/start", {
  method: "POST",
  body: JSON.stringify({
    case_id: "fintech-onboarding"
  })
});
```

Отправка решения:
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

Восстановление state:
```ts
const state = await api("/test/case/state");
```

Если хочешь, следующим сообщением могу сразу написать готовый `testApi.ts` и пример React-хука `useTestCaseFlow()` под этот `/test` контракт.