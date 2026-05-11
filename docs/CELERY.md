# Celery worker guide

This project uses [Celery](https://docs.celeryq.dev/) with **Redis** as the message broker. The FastAPI app **enqueues** work; a separate **worker process** executes tasks asynchronously.

---

## 1. Prerequisites

- **Redis** running and reachable from both the API and the worker (same broker URL).
- Python dependencies installed (`celery` and `redis` are in `requirements.txt`).
- Repository root on `PYTHONPATH` when invoking Celery (run commands from the project root, e.g. `backend/`).

---

## 2. Step-by-step setup

### 2.1 Environment variables

| Variable | Purpose |
|----------|---------|
| `CELERY_BROKER_URL` | Optional. Full Redis URL for Celery (e.g. `redis://localhost:6379/0`). If unset, the app builds a URL from `REDIS_HOST`, `REDIS_PORT`, and `REDIS_DB`. |

**Important:** The **API** and the **worker** must use the **same** broker URL (same host, port, and Redis DB index). Otherwise jobs are published to one Redis and the worker listens on another.

Typical combinations:

| API runs | Worker runs | Broker for API | Broker for worker |
|----------|-------------|----------------|-------------------|
| On host | Docker (`celery_worker`) | `redis://localhost:6379/0` (default if Redis maps `6379`) | Already set in compose: `CELERY_BROKER_URL=redis://redis:6379/0` |
| On host | On host | `redis://localhost:6379/0` | Same |
| Both in Docker (future) | Both in Docker | `redis://redis:6379/0` | Same |

Add to your local `.env` when the API is on the host and Redis is exposed on `localhost:6379`:

```env
CELERY_BROKER_URL=redis://localhost:6379/0
```

(Do not use `redis://redis:6379/0` on the host unless you have that hostname defined, e.g. via extra_hosts.)

### 2.2 Start Redis (Docker)

From the `docker/` directory:

```bash
docker compose up -d redis
```

Or start Redis plus DB and worker together (see below).

### 2.3 Start the Celery worker

**Option A — Worker in Docker (matches `docker/docker-compose.yml`)**

```bash
cd docker
docker compose up celery_worker
```

Logs appear in that terminal, or:

```bash
docker compose logs -f celery_worker
```

**Option B — Worker on your machine**

From the **project root** (directory that contains `app/`):

```bash
celery -A app.core.celery_app worker --loglevel=info
```

Use the same virtualenv as the API if you use one.

### 2.4 Start the API

Run Uvicorn as you normally do. Registration and other code paths call `.delay()` / `apply_async()`; the HTTP response does not wait for the task to finish.

### 2.5 Verify end-to-end

1. Ensure the worker log shows `celery@... ready`.
2. Trigger a task (e.g. `POST /auth/register` with a new email).
3. In **worker** logs (not the API log), you should see Celery task lines and application logs from the task (e.g. welcome email simulation).

---

## 3. Architecture in this repo

| Piece | Location |
|-------|----------|
| Celery application | `app/core/celery_app.py` (`celery_app` instance) |
| Task modules to import on worker startup | Listed in `include=[...]` in `celery_app.py` |
| Example tasks | `app/tasks/email_tasks.py` |
| Enqueue from HTTP | e.g. `app/api/auth.py` — `send_welcome_email.delay(...)` |

The worker entrypoint is always:

```bash
celery -A app.core.celery_app worker --loglevel=info
```

`-A` points at the module that defines `celery_app` (see `app/core/celery_app.py`).

---

## 4. Creating a task

### 4.1 Add the task function

In an existing module under `app/tasks/` (or a new module in that package), import `celery_app` and decorate the function:

```python
from __future__ import annotations

from app.core.celery_app import celery_app


@celery_app.task(name="my_namespace.my_task")
def my_task(user_id: int) -> None:
    # Work runs in the worker process, not in FastAPI.
    ...
```

Guidelines:

- Use **JSON-serializable** arguments (`int`, `str`, `dict`, `list`, etc.). Avoid passing ORM objects or open connections; pass IDs and reload data in the worker if needed.
- Give a stable **`name=`** so renaming the function does not break monitors or routing.
- Keep tasks **idempotent** when possible (safe if run twice).

### 4.2 Register the module with the Celery app

If the task lives in a **new** file, add it to `include` in `app/core/celery_app.py`:

```python
celery_app = Celery(
    "backend",
    broker=settings.celery_broker_url(),
    include=[
        "app.tasks.email_tasks",
        "app.tasks.my_new_tasks",  # add this
    ],
)
```

If you only add functions to a file that is **already** in `include`, you do not need to change `include`.

### 4.3 Enqueue the task from the app

From a route, service, or background hook:

```python
from app.tasks.my_new_tasks import my_task

my_task.delay(user_id=123)
```

`delay(*args, **kwargs)` is shorthand for `apply_async` with default options. The call returns quickly after the message is sent to Redis.

### 4.4 Restart the worker

After adding a new module to `include` or adding new tasks, **restart the Celery worker** so it imports the new code.

---

## 5. Updating an existing task (what to do next)

1. **Edit the task code** in `app/tasks/...` (or wherever the task is defined).
2. **Restart the worker** so it loads the new Python code. Running workers do not hot-reload task bodies.
3. **API process:** If you only changed the **worker** implementation (body of the task), restarting the API is optional. If you changed **signatures**, **task names**, or **enqueue call sites** in FastAPI, restart the API too.
4. **In-flight messages:** Jobs already in the queue were serialized with the old code path in mind. Prefer **backward-compatible** argument changes (new optional kwargs) or accept that old messages may fail and go to retry/dead-letter depending on your Celery configuration.
5. **Docker:** If the worker container bind-mounts the repo (`../:/app` in compose), saving files on the host updates the files in the container, but you still need to **restart the `celery_worker` container** to reload the process.

---

## 6. Creating another new task (checklist)

Use this list whenever you add a different kind of background job:

1. **Create or extend** a module under `app/tasks/` (e.g. `app/tasks/report_tasks.py`).
2. **Define** `@celery_app.task(...)` functions with serializable parameters and a clear `name=`.
3. **Add** the module path to `include=[...]` in `app/core/celery_app.py` if it is a new file.
4. **Call** `task.delay(...)` or `task.apply_async(...)` from the appropriate layer (router, service, etc.). Consider try/except around enqueue if the HTTP path must succeed even when Redis is down.
5. **Restart** the Celery worker (and the API if enqueue code changed).
6. **Confirm** broker URL alignment between API and worker environments.
7. **Optional:** Add logging, metrics, retries (`autoretry_for`, `retry_backoff`), or a result backend if you need task results (currently `task_ignore_result=True` in this project).

---

## 7. Useful commands

| Goal | Command |
|------|---------|
| Run worker (local) | `celery -A app.core.celery_app worker --loglevel=info` |
| List registered tasks | `celery -A app.core.celery_app inspect registered` (worker must be running) |
| Worker logs (Docker) | `docker compose -f docker/docker-compose.yml logs -f celery_worker` |

---

## 8. Troubleshooting

| Symptom | Things to check |
|---------|------------------|
| Task never runs | Same `CELERY_BROKER_URL` / Redis DB for API and worker; worker is running; module is in `include`. |
| Old behavior after edit | Worker not restarted. |
| Import errors on worker start | Typo in `include`, or missing dependency in the worker environment. |
| `ModuleNotFoundError: app` | Run Celery from the **project root**, not from inside `app/`. |

For deeper behavior (retries, chains, beat schedules), see the [official Celery documentation](https://docs.celeryq.dev/en/stable/).
