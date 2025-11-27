# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a modern async REST API for managing todo items with session-based authentication, built with Python's Litestar framework and Redis. The application demonstrates production-ready patterns for async web development with comprehensive OpenAPI documentation.

## Technology Stack

- **Framework**: Litestar (async Python web framework)
- **Server**: Granian with uvloop (high-performance ASGI server)
- **Database**: Redis (for both todo persistence and session storage)
- **Validation**: Pydantic models
- **Package Manager**: uv (fast Python package installer)
- **Testing**: pytest + httpx
- **Python**: 3.11+

## Development Commands

### Initial Setup
```bash
# Install dependencies (creates .venv automatically)
uv sync

# Ensure Redis is running
redis-server
# OR via Docker:
docker run --name redis-todos -p 6379:6379 -d redis:latest
```

### Running the Application
```bash
# Development mode with auto-reload
uv run granian --interface asgi --host 0.0.0.0 --port 8000 --reload app:app

# Server runs on http://localhost:8000
# Interactive API docs at http://localhost:8000/schema
```

### Testing
```bash
# Run all integration tests (requires server running on localhost:8000)
uv run pytest test_integration.py -v

# Run specific test
uv run pytest test_integration.py::TestTodoAPI::test_tag_flow -v

# With coverage
uv run pytest test_integration.py --cov=app
```

### Dependency Management
```bash
# Add new package
uv add package-name

# Update dependencies
uv sync
```

## Architecture Overview

### File Structure
- `app.py` - Main application: routes, models, Redis helpers, and Litestar app configuration
- `test_integration.py` - Integration tests against running API
- `pyproject.toml` - Project metadata and dependencies
- `.env` - Environment configuration (copy from `.env.example`)

### Redis Data Organization

The application uses Redis with the following key patterns:

```
todos:item:{todo_id}          → JSON serialized Todo object
todos:index                   → Set of all todo IDs (for listing)
todos:tags:{todo_id}          → Set of tags attached to a todo
todos:todos_by_tag:{tag}      → Set of todo IDs that have this tag
sess:*                        → Session data (managed by Litestar)
```

**Key Design**: Tag system uses bidirectional indexes for efficient queries:
- Forward index: todo → tags (for "get all tags on this todo")
- Reverse index: tag → todos (for "get all todos with this tag")

### Code Organization in app.py

The file follows a top-down organization:

1. **Configuration** - Environment loading, Redis client setup
2. **Data Models** - Pydantic models (`TodoIn`, `TagIn`) and dataclasses (`Todo`, `LoginIn`)
3. **Redis Helpers** - Low-level CRUD operations for todos and tags
4. **Route Handlers** - HTTP endpoint implementations (decorated with `@get`, `@post`, etc.)
5. **App Configuration** - OpenAPI config and Litestar app initialization

### API Endpoints

**Authentication** (session-based):
- `POST /login` - Create session
- `GET /me` - Get current user
- `DELETE /logout` - Clear session

**Todos** (CRUD):
- `GET /todos` - List all (uses Redis SSCAN for pagination)
- `POST /todos` - Create
- `GET /todos/{id}` - Read one
- `PUT /todos/{id}` - Update
- `DELETE /todos/{id}` - Delete

**Tags** (many-to-many):
- `POST /todos/{id}/tags` - Add tag to todo
- `GET /todos/{id}/tags` - List tags for todo
- `DELETE /todos/{id}/tags/{tag}` - Remove tag from todo
- `GET /tags/{tag}/todos` - Get all todos with tag

**Utility**:
- `GET /healthz` - Health check with Redis connectivity test

## Code Patterns and Conventions

### Naming
- `snake_case` for functions and variables
- `PascalCase` for classes and Pydantic models
- `UPPER_SNAKE` for constants and environment variables
- Private helper functions prefixed with `_` (e.g., `_todo_tags_key()`)

### Async Patterns
- All database operations are async (`await redis.get()`, etc.)
- Route handlers are async functions
- Use Redis pipelines for atomic multi-command operations:
  ```python
  pipe = redis.pipeline()
  pipe.sadd(key1, value1)
  pipe.sadd(key2, value2)
  await pipe.execute()
  ```

### Data Validation
- Use Pydantic models for API input validation (`TodoIn`, `TagIn`)
- Use dataclasses for internal domain objects (`Todo`, `LoginIn`)
- Include field constraints (`min_length`, `max_length`) in Pydantic models

### Error Handling
- Return `Response(content=None, status_code=HTTP_404_NOT_FOUND)` for missing resources
- Pydantic automatically validates input and returns 400 for invalid data
- Use appropriate HTTP status codes: 200 (OK), 201 (Created), 204 (No Content), 404 (Not Found)

## Testing Guidelines

### Integration Test Structure
- Tests are grouped in the `TestTodoAPI` class
- Use `client` fixture for unauthenticated requests
- Use `authenticated_client` fixture for session-based requests
- Clean up created resources within each test to avoid state leakage

### Writing New Tests
1. Create todos within the test (don't rely on existing state)
2. Clean up at the end with `authenticated_client.delete(f"/todos/{todo_id}")`
3. Use descriptive test names: `test_<action>_<expected_outcome>`
4. Assert both status codes and response data

### Test Dependencies
- Tests assume API server running on `http://localhost:8000`
- Tests assume clean Redis state (or namespace isolation via `REDIS_NAMESPACE`)

## Environment Configuration

Required environment variables (set in `.env`):

```env
REDIS_URL=redis://localhost:6379/0    # Redis connection string
REDIS_NAMESPACE=todos:                # Key prefix for isolation
```

Session configuration is hardcoded in `app.py`:
- Cookie name: `sid`
- Max age: 24 hours
- HTTPOnly: true
- SameSite: Lax

## Adding New Features

### Adding a New Todo Field
1. Update `Todo` dataclass in `app.py`
2. Update `TodoIn` Pydantic model with validation rules
3. Ensure `save_todo()` serializes the new field
4. Add tests in `test_integration.py`

### Adding a New Endpoint
1. Define route handler function with appropriate decorator (`@get`, `@post`, etc.)
2. Add type hints for automatic OpenAPI schema generation
3. Register handler in the `route_handlers` list in `Litestar()` initialization
4. Add integration tests
5. Verify in OpenAPI docs at `/schema`

### Adding a New Redis Data Structure
1. Create key helper function (e.g., `_my_key(id: str) -> str`)
2. Implement CRUD helper functions (async)
3. Use pipelines for multi-step atomic operations
4. Document the key pattern in this file

## Common Gotchas

1. **Missing delete_todo_handler**: The delete endpoint handler must be defined before being registered in `route_handlers`
2. **Redis namespace**: All keys use `REDIS_NAMESPACE` prefix - don't flush Redis in development
3. **Session cookies**: Sessions are server-side; only the session ID cookie is sent to client
4. **Async/await**: All Redis operations must be awaited; forgetting `await` causes silent failures
5. **Test isolation**: Integration tests share Redis; use unique data or clean up to avoid conflicts
6. **OpenAPI registration**: New route handlers must be added to the `route_handlers` list in `Litestar()` initialization

## Documentation

The API provides 5 interactive documentation interfaces:
- Swagger UI (primary): http://localhost:8000/schema
- ReDoc: http://localhost:8000/schema/redoc
- Stoplight Elements: http://localhost:8000/schema/elements
- RapiDoc: http://localhost:8000/schema/rapidoc
- OpenAPI JSON: http://localhost:8000/schema/openapi.json

All are auto-generated from route decorators and type hints.
