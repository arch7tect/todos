# Repository Guidelines

## Project Structure & Modules
- `app.py` holds the Litestar application, routes, and Redis-backed models; keep new routes colocated with related helpers.
- `test_integration.py` exercises the running API against localhost:8000; add new integration cases here or next to related features.
- `pyproject.toml` and `uv.lock` manage dependencies; update both via `uv` when adding packages.
- Environment files live at `.env` (copy from `.env.example`); Redis is required for sessions and todo storage.

## Build, Test, and Development Commands
- Install deps: `uv sync` (creates a virtual env and installs locked versions).
- Run API in dev: `uv run granian --interface asgi --host 0.0.0.0 --port 8000 --reload app:app` (requires Redis running locally or via Docker `redis-server` / `docker run ... redis:latest`).
- Run integration suite: `uv run pytest test_integration.py -v` (assumes server on localhost:8000).
- Optional coverage: `uv run pytest test_integration.py --cov=app`.

## Coding Style & Naming Conventions
- Python 3.11+, 4-space indentation, line length target 100 (per `pyproject.toml`).
- Prefer typed function signatures and dataclasses/Pydantic models for request/response schemas.
- Use `snake_case` for functions/vars, `PascalCase` for classes and Pydantic models, `UPPER_SNAKE` for constants/env keys.
- Keep responses JSON-serializable and validate input via Pydantic models similar to `TodoIn`.

## Testing Guidelines
- Integration tests rely on a running server and clean Redis. Clear created todos within each test as shown to avoid cross-test state.
- Name tests descriptively (e.g., `test_update_todo_sets_done_flag`) and group flows inside `TestTodoAPI` or new classes per endpoint area.
- For new endpoints, add login/setup helpers to fixtures instead of repeating request code.

## Commit & Pull Request Guidelines
- Use concise, imperative commit messages (e.g., "Add Redis session TTL check"). Group related changes per commit.
- PRs should describe behavior changes, include steps to reproduce/verify, and note any new env vars or migrations.
- Link relevant issues, and include test evidence (`pytest` output or manual steps) when behavior changes.

## Environment & Security Notes
- Do not commit secrets; load values via `.env` and reference `REDIS_URL`/`REDIS_NAMESPACE` in code.
- Redis powers both todos and sessions—ensure namespaces stay consistent; avoid flushing Redis in tests outside isolated environments.
- When exposing publicly, set session cookies to `secure=True` behind TLS and review CORS/auth defaults.
