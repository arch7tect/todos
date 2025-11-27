# Todos API

Async REST API for managing todos with tags. Built with Python, Litestar, and Redis.

## Tech Stack

- **Framework**: [Litestar 2.18](https://litestar.dev/)
- **Server**: [Granian](https://github.com/emmett-framework/granian) with uvloop
- **Database**: [Redis 8.4](https://redis.io/)
- **Validation**: [Pydantic v2](https://pydantic.dev/) (Rust-powered)
- **JSON**: [orjson](https://github.com/ijl/orjson) (9.5x faster)
- **Storage**: [MessagePack](https://msgpack.org/) (binary serialization)
- **Package Manager**: [uv](https://github.com/astral-sh/uv)
- **Testing**: [pytest](https://pytest.org/) + [httpx](https://www.python-httpx.org/)

## Prerequisites

- Python 3.11+
- Redis server
- uv package manager

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/arch7tect/todos.git
cd todos
uv sync
```

### 2. Start Redis

```bash
# Homebrew (macOS)
brew install redis && brew services start redis

# Docker
docker run --name redis-todos -p 6379:6379 -d redis:latest
```

### 3. Run the API

```bash
uv run granian --interface asgi --host 0.0.0.0 --port 8000 --reload app:app
```

API available at: http://localhost:8000

## API Documentation

Interactive documentation:
- **Swagger UI**: http://localhost:8000/schema
- **ReDoc**: http://localhost:8000/schema/redoc
- **OpenAPI JSON**: http://localhost:8000/schema/openapi.json

## API Endpoints

### Health & Auth
- `GET /healthz` - Health check
- `POST /login` - Create session
- `GET /me` - Get current user
- `DELETE /logout` - Clear session

### Todos (tags embedded in all responses)
- `GET /todos` - List all todos
- `POST /todos` - Create todo
- `GET /todos/{id}` - Get todo
- `PUT /todos/{id}` - Update todo
- `DELETE /todos/{id}` - Delete todo

### Tags
- `POST /todos/{id}/tags` - Add tag
- `GET /todos/{id}/tags` - Get tags
- `DELETE /todos/{id}/tags/{tag}` - Remove tag
- `GET /tags/{tag}/todos` - Query by tag

## Usage Examples

### Create and Tag a Todo

```bash
# Create
curl -X POST http://localhost:8000/todos \
  -H "Content-Type: application/json" \
  -d '{"title":"Buy groceries","done":false}'
# Response: {"id":"abc-123","title":"Buy groceries","done":false,"tags":[]}

# Add tag
curl -X POST http://localhost:8000/todos/abc-123/tags \
  -H "Content-Type: application/json" \
  -d '{"tag":"shopping"}'

# Get todo (tags embedded)
curl http://localhost:8000/todos/abc-123
# Response: {"id":"abc-123","title":"Buy groceries","done":false,"tags":["shopping"]}
```

### Query by Tag

```bash
curl http://localhost:8000/tags/shopping/todos
```

## Testing

```bash
# Run all tests
uv run pytest test_integration.py -v

# Run specific test
uv run pytest test_integration.py::TestTodoAPI::test_tag_flow -v

# With coverage
uv run pytest test_integration.py --cov=app
```

All 13 tests pass in ~0.3 seconds.

## Architecture

### Data Models

**Input Models** (request bodies):
- `TodoCreate`, `TodoUpdate`, `TagCreate`, `LoginRequest`

**Output Models** (responses):
- `TodoOut`, `UserOut`

### Storage Architecture

```
HTTP Request
  ↓ orjson (9.5x faster)
Litestar + Pydantic
  ↓ MessagePack (22% smaller)
Redis (binary mode)
```

### Redis Key Structure

```
todos:item:{id}           → MessagePack binary (todo data)
todos:index               → Set of todo IDs
todos:tags:{id}           → Set of tags for todo
todos:todos_by_tag:{tag}  → Set of todo IDs with tag
sess:{id}                 → Session data
```

## Configuration

Environment variables (optional, defaults shown):

```bash
REDIS_URL=redis://localhost:6379/0
REDIS_NAMESPACE=todos:
```

## Performance Benchmarks

**JSON Serialization (100k iterations):**
- stdlib json: 0.108s
- Pydantic v2: 0.065s (1.7x)
- orjson: 0.011s (9.5x)

**Storage (per todo):**
- JSON text: 114 bytes
- MessagePack: 89 bytes (22% smaller)

**API Calls:**
- Before: 2 calls (GET todo + GET tags)
- After: 1 call (50% reduction)

## Project Structure

```
todos/
├── app.py                 # Main application
├── test_integration.py    # Integration tests
├── pyproject.toml         # Project configuration
├── uv.lock               # Locked dependencies
├── .gitignore            # Git ignore rules
└── README.md             # Documentation
```

## Production Deployment

### Environment Variables

```bash
REDIS_URL=redis://production-host:6379/0
REDIS_NAMESPACE=todos:
```

### Security

- Set `secure=True` for session cookies behind HTTPS
- Use Redis password in production
- Configure CORS if needed

## License

MIT License. See [LICENSE](LICENSE) file for details.
