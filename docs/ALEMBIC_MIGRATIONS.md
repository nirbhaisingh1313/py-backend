# Alembic Migrations (this repo)

This project uses:

- **SQLAlchemy (async)**: models live under `app/models/`
- **Alembic**: migrations live under `alembic/versions/`
- **Database URL**: comes from `.env` (`DATABASE_URL=...`)

Alembic reads your DB URL from `.env` inside `alembic/env.py`, converts it to an async URL (`postgresql+asyncpg://...`), then runs migrations against that database.

---

## What is a migration?

A migration is a versioned, replayable set of schema changes (create table, add column, add index, etc.).

- **Source of truth for schema**: your SQLAlchemy models (e.g. `app/models/user.py`)
- **Source of truth for history**: Alembic migration scripts (e.g. `alembic/versions/<rev>_*.py`)
- **Current DB version**: stored in the table `public.alembic_version`

---

## Before you run anything: confirm which Postgres you’re targeting

On macOS it’s common to have **Homebrew Postgres** and **Docker Postgres** both available.

### Check what `DATABASE_URL` points to

```bash
cd /Users/nirbhaisingh/Documents/playground/backend
cat .env
```

Example:

```bash
DATABASE_URL=postgresql://admin:admin@localhost:5432/app_db
```

### Confirm the server you’ll migrate (very important)

If your URL uses `localhost:5432`, verify what server that is:

```bash
export PGPASSWORD=admin
psql -h localhost -p 5432 -U admin -d app_db -c "select version();"
```

- If you see **Homebrew** in the output → you are migrating **local Postgres**
- If you see **Debian/Linux** in the output → you are migrating **Docker Postgres**

To inspect Docker directly (bypasses port confusion):

```bash
docker exec -i postgres_db psql -U admin -d app_db -c "select version();"
```

---

## Common Alembic commands

Run these from the repo root:

```bash
cd /Users/nirbhaisingh/Documents/playground/backend
source venv/bin/activate
```

### Check current revision applied to the DB

```bash
alembic current
```

### See full migration history

```bash
alembic history
```

### Apply all pending migrations to latest (recommended)

```bash
alembic upgrade head
```

### Downgrade (roll back) one migration

```bash
alembic downgrade -1
```

---

## How autogenerate works in this repo

When you run:

```bash
alembic revision --autogenerate -m "some message"
```

Alembic does:

1. **Imports your model metadata** (`Base.metadata`)
2. **Connects to the target DB**
3. **Reflects the current DB schema**
4. **Diffs models vs DB**
5. **Writes a new migration script** into `alembic/versions/`

Important: autogenerate is *not magic*. Always review the generated script before applying it.

---

## Example: add a `name` column to `users`

Goal: add a nullable `name` column (or non-nullable, depending on your needs).

### Step 1: update the model

Edit `app/models/user.py` and add a column.

#### Option A (safe): nullable `name`

This is easiest because it doesn’t require backfilling existing rows.

```python
name: Mapped[str | None] = mapped_column(String(200), nullable=True)
```

#### Option B (strict): non-nullable `name`

If you need `name` required, you must decide:

- provide a server default, **or**
- backfill existing rows in the migration before making it non-nullable

Example (model):

```python
name: Mapped[str] = mapped_column(String(200), nullable=False)
```

If the table already has rows, this will require a custom migration (see “Backfill” below).

### Step 2: generate a migration

```bash
cd /Users/nirbhaisingh/Documents/playground/backend
source venv/bin/activate
alembic revision --autogenerate -m "add user name"
```

This creates a file like:

```
alembic/versions/<revision>_add_user_name.py
```

### Step 3: review the migration file

Open the generated file and confirm it contains what you expect, typically:

```python
op.add_column("users", sa.Column("name", sa.String(length=200), nullable=True))
```

If it generated more changes than expected, stop and fix your model imports/metadata wiring before proceeding.

### Step 4: apply the migration

```bash
alembic upgrade head
```

### Step 5: verify in the DB

#### If your DB is the one on localhost:5432

```bash
export PGPASSWORD=admin
psql -h localhost -p 5432 -U admin -d app_db -c "\\d users"
```

#### If you want to verify inside Docker

```bash
docker exec -i postgres_db psql -U admin -d app_db -c "\\d users"
```

---

## Backfill pattern (when adding NOT NULL columns)

If you want `name` to be `NOT NULL` and the table already has data:

1. Add the column as **nullable**
2. Backfill data
3. Alter column to **non-nullable**

In Alembic, that often looks like:

```python
op.add_column("users", sa.Column("name", sa.String(length=200), nullable=True))
op.execute("UPDATE users SET name = 'Unknown' WHERE name IS NULL")
op.alter_column("users", "name", nullable=False)
```

This avoids breaking existing rows.

---

## Troubleshooting

### 1) `\dt` shows no tables but Alembic says “head”

This usually means you’re checking a *different DB instance* than the one Alembic migrated.

Use `select version()` to identify which Postgres you’re hitting:

```bash
export PGPASSWORD=admin
psql -h localhost -p 5432 -U admin -d app_db -c "select version();"
```

And verify Alembic’s target is the same `.env` `DATABASE_URL`.

### 2) Docker is running but `psql -h localhost` still shows Homebrew

You likely have **both** listening on port 5432.

Check listeners:

```bash
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

Fix by either:

- stopping Homebrew Postgres, or
- changing Docker port to e.g. `5433:5432` and updating `.env`

### 3) `database "app_db" does not exist`

Create it inside Docker:

```bash
docker exec -i postgres_db createdb -U admin app_db
```

Or locally:

```bash
export PGPASSWORD=admin
createdb -h localhost -p 5432 -U admin app_db
```

---

## Quick “daily workflow” checklist

When you change models:

1. Update model(s) under `app/models/`
2. Generate migration:
   - `alembic revision --autogenerate -m "..." `
3. Review the generated migration file
4. Apply:
   - `alembic upgrade head`
5. Verify:
   - `alembic current`
   - `psql ... -c "\\dt"` / `\\d <table>`

