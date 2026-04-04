# Frontend Guide for `/test3` API

`main3.py` решает главную проблему `main2.py`: теперь у каждого пользователя своё состояние, привязанное к `client_id`.

Для фронта это должно работать так:

- при первом открытии страницы фронт генерирует `client_id`
- сохраняет его в `sessionStorage`
- передаёт `client_id` в каждый запрос
- backend сам восстанавливает активный кейс, сообщения и solved-progress именно этого пользователя

Важно:

- отдельный `session_id` для `/test3` не нужен
- один `client_id` = одно пользовательское состояние
- если открыть новую вкладку, можно:
  - либо использовать тот же `client_id`, если нужен общий прогресс в рамках браузера
  - либо генерировать новый, если нужна полностью отдельная сессия

## Base URL

- Local: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- OpenAPI: `http://localhost:8000/openapi.json`

## Что хранить на фронте

Минимум:

- `clientId`
- `cases`
- `activeCase`
- `messages`
- `lastEvaluation`
- `progress`
- `mode`
- `loading`
- `error`

## Как получить `client_id`

Простой вариант:

```ts
function getClientId(): string {
  const storageKey = "cu_business_trainer_client_id";
  const existing = sessionStorage.getItem(storageKey);

  if (existing) {
    return existing;
  }

  const created = crypto.randomUUID();
  sessionStorage.setItem(storageKey, created);
  return created;
}
```

## Базовый fetch helper

```ts
const API_BASE = "http://localhost:8000";
const clientId = getClientId();

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

## Общий flow

1. На загрузке страницы:
   - `GET /test3/health`
   - `GET /test3/case/state?client_id=...`
   - `GET /test3/cases/progress?client_id=...`
   - `GET /test3/cases`
2. Пользователь выбирает кейс:
   - `POST /test3/case/start`
3. Пользователь отправляет решение:
   - `POST /test3/case/submit`
4. Пользователь задаёт уточняющий вопрос:
   - `POST /test3/case/followup`
5. Для solved/unsolved:
   - `POST /test3/cases/progress/mark-solved`
   - `POST /test3/cases/progress/unmark-solved`
   - `POST /test3/cases/progress/reset`

## Endpoints

### `GET /test3/health`

Проверка режима backend.

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

### `GET /test3/cases`

Список всех кейсов.

### `GET /test3/cases/{case_id}`

Полная карточка кейса.

### `GET /test3/cases/progress?client_id=...`

Возвращает solved/unsolved progress конкретного пользователя.

Пример:

```json
{
  "solved_cases": [],
  "unsolved_cases": [],
  "solved_count": 0,
  "unsolved_count": 5
}
```

### `POST /test3/cases/progress/mark-solved`

Явно помечает кейс как solved у конкретного пользователя.

Request:

```json
{
  "client_id": "7b2f8b9d-0d9a-4e65-9930-40d7a9d70455",
  "case_id": "mentor-matching-platform"
}
```

### `POST /test3/cases/progress/unmark-solved`

Убирает кейс из solved у конкретного пользователя.

Request:

```json
{
  "client_id": "7b2f8b9d-0d9a-4e65-9930-40d7a9d70455",
  "case_id": "mentor-matching-platform"
}
```

### `POST /test3/cases/progress/reset`

Полностью очищает solved-progress пользователя.

Request:

```json
{
  "client_id": "7b2f8b9d-0d9a-4e65-9930-40d7a9d70455"
}
```

### `GET /test3/case/state?client_id=...`

Возвращает текущее состояние кейсовой сессии именно этого пользователя.

Если пользователь ещё не стартовал кейс:

```json
{
  "mode": "mock",
  "active_case": null,
  "messages": [],
  "last_evaluation": null
}
```

### `POST /test3/case/start`

Запускает кейс для конкретного пользователя.

Request:

```json
{
  "client_id": "7b2f8b9d-0d9a-4e65-9930-40d7a9d70455",
  "case_id": "mentor-matching-platform"
}
```

Ответ:

```json
{
  "mode": "mock",
  "case": {
    "id": "mentor-matching-platform",
    "title": "Платформа персонального менторства от выпускников",
    "theme": "careertech",
    "short_description": "Нужно помочь студентам быстрее находить выпускников-менторов",
    "difficulty": "medium",
    "tags": ["карьера", "менторство"],
    "background": "У университета большая база выпускников",
    "task": "Предложите MVP продукта",
    "reference_solution_summary": "Сделать умный матчинг",
    "evaluation_criteria": [
      "problem_clarity",
      "market_business_logic",
      "feasibility",
      "differentiation"
    ]
  },
  "welcome_message": "Кейс активирован. Пришли решение, и я оценю его.",
  "messages": [
    {
      "role": "assistant",
      "content": "Кейс активирован. Пришли решение, и я оценю его."
    }
  ]
}
```

Важно:

- `start` сбрасывает только текущую активную кейсовую сессию пользователя
- solved-progress этого же пользователя сохраняется
- состояние других пользователей не затрагивается

### `POST /test3/case/submit`

Отправляет решение по активному кейсу текущего пользователя.

Request:

```json
{
  "client_id": "7b2f8b9d-0d9a-4e65-9930-40d7a9d70455",
  "solution_text": "Сначала делаем MVP, валидируем спрос и считаем time-to-value."
}
```

Response shape:

- `mode`
- `case`
- `summary`
- `score`
- `criteria_scores`
- `strengths`
- `weaknesses`
- `improvements`
- `novel_ideas`
- `messages`

После `submit` кейс автоматически попадает в solved именно у этого пользователя.

### `POST /test3/case/followup`

Уточняющий вопрос после `submit`.

Request:

```json
{
  "client_id": "7b2f8b9d-0d9a-4e65-9930-40d7a9d70455",
  "message": "Какой первый эксперимент лучше сделать?"
}
```

Response shape:

- `mode`
- `case`
- `reply`
- `risks`
- `next_questions`
- `advice`
- `messages`

## Рекомендуемый frontend flow

### При загрузке

```ts
const clientId = getClientId();

const [health, state, progress, cases] = await Promise.all([
  api("/test3/health"),
  api(`/test3/case/state?client_id=${encodeURIComponent(clientId)}`),
  api(`/test3/cases/progress?client_id=${encodeURIComponent(clientId)}`),
  api("/test3/cases")
]);
```

### Старт кейса

```ts
const started = await api("/test3/case/start", {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    case_id: selectedCaseId
  })
});
```

### Отправка решения

```ts
const evaluation = await api("/test3/case/submit", {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    solution_text: userSolution
  })
});
```

### Follow-up

```ts
const followup = await api("/test3/case/followup", {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    message: userQuestion
  })
});
```

### Явно пометить solved

```ts
const progress = await api("/test3/cases/progress/mark-solved", {
  method: "POST",
  body: JSON.stringify({
    client_id: clientId,
    case_id: selectedCaseId
  })
});
```

## Ошибки

- `422`, если не передан `client_id`
- `404`, если кейс не найден
- `400`, если вызвать `submit` без `start`
- `400`, если вызвать `followup` до `submit`
- `503`, если выбран `yandex`, но backend не настроен
- `502`, если упал запрос к Yandex API

## Главное правило для фронта

Во все user-specific запросы обязательно передавайте один и тот же `client_id`, который хранится в `sessionStorage`.

Тогда backend будет вести себя как простая персональная сессия:

- свой активный кейс
- своя история сообщений
- свой solved-progress
- без конфликтов с другими пользователями
