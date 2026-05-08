# Request lifecycle (FastAPI + async DB + JWT)

This describes what happens for a **protected** route such as `GET /users/me`, which declares:

`current_user: User = Depends(get_current_user)`

---

### 1. Request arrives

The ASGI server (e.g. Uvicorn) hands FastAPI a request: method, path, headers, body. FastAPI picks the matching route (or returns 404).

---

### 2. Dependencies execute (before your route function)

For each endpoint, FastAPI builds a **dependency graph** and runs dependencies **before** the route handler. Anything declared with `Depends(...)` is resolved here.

For `get_current_user`, FastAPI must satisfy:

- **`Request`** — injected automatically (used to read raw headers when needed).
- **`get_db`** — yields an `AsyncSession`.
- **`HTTPBearer`** (`http_bearer`) — reads `Authorization`, expects Bearer credentials for OpenAPI/Swagger.

Then **`get_current_user`** runs: it uses the session and the bearer credentials together.

Order note: sub-dependencies of `get_current_user` run first; you don’t manually orchestrate that in the route.

---

### 3. DB session is created

`get_db` is an **async generator** dependency:

- Entering `async with AsyncSessionLocal() as session` **opens** a session.
- `yield session` passes it to dependents (`get_current_user`).

No route handler runs until the dependencies needed for that handler have finished successfully.

---

### 4. Auth is validated

Roughly in sequence inside **`get_current_user`**:

1. **`HTTPBearer`** has already parsed `Authorization: Bearer <token>` (or your code treats missing/invalid scheme as 401).
2. **`decode_access_token`** checks signature, algorithm, and **`exp`** (via python-jose / JWT rules).
3. **`user_id`** is read from the payload and checked.
4. A **DB query** loads `User` by id; missing user → 401.

If any step fails, FastAPI raises **`HTTPException`** and **your route handler is not called**.

---

### 5. Route handler runs

Only after dependencies succeed, FastAPI calls your function, e.g.:

```python
async def read_current_user(current_user: User = Depends(get_current_user)) -> UserSuccessResponse:
    ...
```

Here `current_user` is the **`User`** instance returned by `get_current_user`.

---

### 6. Response is serialized

If you set **`response_model=SomeSchema`**, FastAPI/Pydantic:

- Validates the return value against that schema.
- Serializes it to JSON for the HTTP body.

Wrong shape or validation errors become a **server error** or validation response depending on context—so keeping return types aligned with `response_model` matters.

---

### 7. Session cleanup

When the request handling finishes, FastAPI unwinds dependencies in reverse order.

For **`get_db`**, execution continues **after** the `yield`: leaving the `async with` block **closes** the session (connections go back to the pool). You typically **do not** commit here unless you’ve explicitly designed transactions inside routes/services.

---

## Sanity checklist when testing

- **Without** `Authorization`: expect **401** and no handler execution.
- **With** bad/expired token: **401** from JWT decode path.
- **With** valid token but deleted user: **401** from “user not found”.
- **Swagger**: use **Authorize** with the raw JWT from `POST /auth/login` (Swagger sends `Bearer` for you).

---

## Public routes (e.g. `POST /auth/login`)

Steps **3–4** differ: there is no `get_current_user`, so no Bearer dependency and no “current user” query—only whatever `Depends(get_db)` or other deps that route declares.
