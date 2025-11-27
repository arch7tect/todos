from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import msgpack
from dotenv import load_dotenv
from litestar import Litestar, delete, get, post, put
from litestar.middleware.session.server_side import ServerSideSessionConfig
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import (
    RapidocRenderPlugin,
    RedocRenderPlugin,
    StoplightRenderPlugin,
    SwaggerRenderPlugin,
)
from litestar.response import Response
from litestar.status_codes import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_204_NO_CONTENT,
    HTTP_404_NOT_FOUND,
)
from litestar.stores.redis import RedisStore
from pydantic import BaseModel, Field
from redis import asyncio as aioredis  # redis>=5

# --- env / redis config ---
_ = load_dotenv()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_NAMESPACE = os.getenv("REDIS_NAMESPACE", "todos:")

# import debugpy
# Enable debugpy on port 5678
# debugpy.listen(("0.0.0.0", 5678))
# print("🐛 Debugger listening on port 5678...")

# Async Redis client for app data (binary mode for msgpack)
redis = aioredis.from_url(REDIS_URL, decode_responses=False)

# Store for server-side sessions
session_store = RedisStore.with_client(namespace="sess:")

# Litestar v2: cookie name is `key`, and `store` must match app.stores key below
session_mw = ServerSideSessionConfig(
    store="sessions",
    key="sid",
    max_age=60 * 60 * 24,  # 1 day
    secure=False,  # True in prod behind TLS
    httponly=True,
    samesite="lax",
).middleware


# --- models ---


# Input Models (what clients send to API)
class TodoCreate(BaseModel):
    """Request body for creating a new todo."""

    title: str = Field(min_length=1, max_length=200, description="Todo title")
    done: bool = Field(default=False, description="Completion status")


class TodoUpdate(BaseModel):
    """Request body for updating an existing todo."""

    title: str = Field(min_length=1, max_length=200, description="Todo title")
    done: bool = Field(default=False, description="Completion status")


class TagCreate(BaseModel):
    """Request body for adding a tag to a todo."""

    tag: str = Field(min_length=1, max_length=50, description="Tag name")


class LoginRequest(BaseModel):
    """Request body for user login."""

    name: str = Field(description="Username")


# Output Models (what API returns to clients)
class TodoOut(BaseModel):
    """Todo response returned by API endpoints."""

    id: str = Field(description="Unique todo identifier")
    title: str = Field(description="Todo title")
    done: bool = Field(description="Completion status")
    tags: list[str] = Field(default_factory=list, description="Associated tags")

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    """User information response."""

    name: str = Field(description="Username")


# Domain Model (internal representation with storage methods)
class Todo(BaseModel):
    """Internal todo model with persistence logic."""

    id: str
    title: str
    done: bool = False
    tags: list[str] = Field(default_factory=list)

    @staticmethod
    def key(todo_id: str) -> str:
        return f"{REDIS_NAMESPACE}item:{todo_id}"

    @staticmethod
    def index_key() -> str:
        return f"{REDIS_NAMESPACE}index"

    def dumps(self) -> bytes:
        """Serialize to MessagePack binary format for Redis storage."""
        return msgpack.packb(self.model_dump(), use_bin_type=True)

    @staticmethod
    def loads(data: bytes) -> "Todo":
        """Deserialize from MessagePack binary format."""
        return Todo.model_validate(msgpack.unpackb(data, raw=False))

    def to_out(self) -> TodoOut:
        """Convert to API output model."""
        return TodoOut(id=self.id, title=self.title, done=self.done, tags=self.tags)


# ----- Tag helpers (many‑to‑many) -----


# Redis key helpers for tags
def _todo_tags_key(todo_id: str) -> str:
    return f"{REDIS_NAMESPACE}tags:{todo_id}"


def _tag_todos_key(tag: str) -> str:
    return f"{REDIS_NAMESPACE}todos_by_tag:{tag}"


async def get_tags_for_todo(todo_id: str) -> list[str]:
    """Return a list of tags attached to the given todo."""
    members = await redis.smembers(_todo_tags_key(todo_id))
    # Decode bytes to strings
    return [m.decode("utf-8") if isinstance(m, bytes) else m for m in members]


# --- data helpers (Redis persistence) ---
async def save_todo(todo: Todo) -> None:
    pipe = redis.pipeline()
    _ = pipe.sadd(Todo.index_key(), todo.id)
    _ = pipe.set(Todo.key(todo.id), todo.dumps())
    _ = await pipe.execute()


async def get_todo(todo_id: str) -> Todo | None:
    data = await redis.get(Todo.key(todo_id))
    if not data:
        return None
    todo = Todo.loads(data)
    # Fetch tags for this todo
    todo.tags = await get_tags_for_todo(todo_id)
    return todo


async def delete_todo(todo_id: str) -> None:
    # Get tags to clean up reverse indexes
    tags = await redis.smembers(_todo_tags_key(todo_id))

    pipe = redis.pipeline()
    _ = pipe.srem(Todo.index_key(), todo_id)
    _ = pipe.delete(Todo.key(todo_id))
    _ = pipe.delete(_todo_tags_key(todo_id))

    # Clean up reverse indexes (tag -> todos)
    for tag in tags:
        # Decode tag if it's bytes
        tag_str = tag.decode("utf-8") if isinstance(tag, bytes) else tag
        _ = pipe.srem(_tag_todos_key(tag_str), todo_id)

    _ = await pipe.execute()


async def list_todos(limit: int = 500) -> list[Todo]:
    """Return a list of Todo objects, optionally limited."""
    items: list[Todo] = []
    cursor = 0
    ids: list[bytes] = []
    while True:
        cursor, batch = await redis.sscan(Todo.index_key(), cursor=cursor, count=256)
        ids.extend(batch)
        if cursor == 0 or len(ids) >= limit:
            break
    if not ids:
        return []
    ids = ids[:limit]

    # Decode todo IDs from bytes
    todo_ids = [tid.decode("utf-8") if isinstance(tid, bytes) else tid for tid in ids]

    # Batch fetch todos and their tags efficiently
    values = await redis.mget([Todo.key(tid) for tid in todo_ids])

    # Batch fetch tags for all todos using pipeline
    pipe = redis.pipeline()
    for tid in todo_ids:
        pipe.smembers(_todo_tags_key(tid))
    tags_results = await pipe.execute()

    # Combine todos with their tags
    for i, v in enumerate(values):
        if v:
            todo = Todo.loads(v)
            # Decode tags from bytes
            todo.tags = (
                [t.decode("utf-8") if isinstance(t, bytes) else t for t in tags_results[i]]
                if tags_results[i]
                else []
            )
            items.append(todo)
    return items


async def add_tag_to_todo(todo_id: str, tag: str) -> None:
    """Add *tag* to a todo and create the reverse link."""
    pipe = redis.pipeline()
    pipe.sadd(_todo_tags_key(todo_id), tag)
    pipe.sadd(_tag_todos_key(tag), todo_id)
    await pipe.execute()


async def remove_tag_from_todo(todo_id: str, tag: str) -> None:
    """Remove *tag* from a todo and clean the reverse link."""
    pipe = redis.pipeline()
    pipe.srem(_todo_tags_key(todo_id), tag)
    pipe.srem(_tag_todos_key(tag), todo_id)
    await pipe.execute()


async def get_todos_by_tag(tag: str, limit: int = 500) -> list[Todo]:
    """Return Todo objects that have the specified *tag*.
    Uses the reverse‑lookup set and then bulk‑gets the Todo JSON.
    """
    ids = await redis.smembers(_tag_todos_key(tag))
    if not ids:
        return []
    ids = list(ids)[:limit]

    # Decode todo IDs from bytes
    todo_ids = [tid.decode("utf-8") if isinstance(tid, bytes) else tid for tid in ids]

    # Batch fetch todos and their tags
    values = await redis.mget([Todo.key(tid) for tid in todo_ids])

    # Batch fetch tags for all todos using pipeline
    pipe = redis.pipeline()
    for tid in todo_ids:
        pipe.smembers(_todo_tags_key(tid))
    tags_results = await pipe.execute()

    todos: list[Todo] = []
    for i, v in enumerate(values):
        if v:
            todo = Todo.loads(v)
            # Decode tags from bytes
            todo.tags = (
                [t.decode("utf-8") if isinstance(t, bytes) else t for t in tags_results[i]]
                if tags_results[i]
                else []
            )
            todos.append(todo)
    return todos


# ----- End of tag helpers -----


# --- routes ---
@get("/healthz")
async def healthz() -> dict[str, Any]:
    ok = await redis.ping()
    return {"ok": bool(ok)}


@post("/login", status_code=HTTP_201_CREATED)
async def login(data: LoginRequest, request: Any) -> UserOut:
    """Login and create a session."""
    user = data.name.strip()
    if not user:
        return UserOut(name="")
    request.session["user"] = user
    return UserOut(name=user)


@get("/me", status_code=HTTP_200_OK)
async def me(request: Any) -> UserOut:
    """Get current user information."""
    return UserOut(name=request.session.get("user", ""))


@delete("/logout", status_code=HTTP_204_NO_CONTENT)
async def logout(request: Any) -> Response[None]:
    """Logout and clear session."""
    request.session.clear()
    return Response(None, status_code=HTTP_204_NO_CONTENT)


@get("/todos")
async def list_todos_handler() -> list[TodoOut]:
    """List all todos with their tags."""
    todos = await list_todos()
    return [todo.to_out() for todo in todos]


@post("/todos", status_code=HTTP_201_CREATED)
async def create_todo_handler(data: TodoCreate) -> TodoOut:
    """Create a new todo."""
    todo = Todo(id=str(uuid4()), title=data.title, done=data.done)
    await save_todo(todo)
    return todo.to_out()


@get("/todos/{todo_id:str}")
async def get_todo_handler(todo_id: str) -> TodoOut | Response[None]:
    """Get a specific todo by ID."""
    todo = await get_todo(todo_id)
    return todo.to_out() if todo else Response(content=None, status_code=HTTP_404_NOT_FOUND)


@put("/todos/{todo_id:str}")
async def update_todo_handler(todo_id: str, data: TodoUpdate) -> TodoOut | Response[None]:
    """Update an existing todo."""
    todo = await get_todo(todo_id)
    if not todo:
        return Response(content=None, status_code=HTTP_404_NOT_FOUND)
    todo.title = data.title
    todo.done = data.done
    await save_todo(todo)
    return todo.to_out()


@delete("/todos/{todo_id:str}", status_code=HTTP_204_NO_CONTENT)
async def delete_todo_handler(todo_id: str) -> Response[None]:
    await delete_todo(todo_id)
    return Response(content=None, status_code=HTTP_204_NO_CONTENT)


@post("/todos/{todo_id:str}/tags", status_code=HTTP_201_CREATED)
async def add_tag_handler(todo_id: str, data: TagCreate) -> Response[None]:
    """Add a tag to a todo."""
    # Ensure todo exists
    todo = await get_todo(todo_id)
    if not todo:
        return Response(content=None, status_code=HTTP_404_NOT_FOUND)
    await add_tag_to_todo(todo_id, data.tag)
    return Response(None, status_code=HTTP_201_CREATED)


@get("/todos/{todo_id:str}/tags")
async def get_tags_handler(todo_id: str) -> list[str]:
    """Get all tags for a specific todo."""
    # If todo does not exist, return 404
    todo = await get_todo(todo_id)
    if not todo:
        return []  # alternatively could 404, but keep simple
    return await get_tags_for_todo(todo_id)


@delete("/todos/{todo_id:str}/tags/{tag:str}")
async def remove_tag_handler(todo_id: str, tag: str) -> Response[None]:
    """Remove a specific tag from a todo."""
    # Ensure todo exists
    todo = await get_todo(todo_id)
    if not todo:
        return Response(content=None, status_code=HTTP_404_NOT_FOUND)
    await remove_tag_from_todo(todo_id, tag)
    return Response(None, status_code=HTTP_204_NO_CONTENT)


@get("/tags/{tag:str}/todos")
async def get_todos_by_tag_handler(tag: str) -> list[TodoOut]:
    """Get all todos that have a specific tag."""
    todos = await get_todos_by_tag(tag)
    return [todo.to_out() for todo in todos]


openapi_config = OpenAPIConfig(
    title="Todos API",
    version="0.1.0",
    render_plugins=[
        SwaggerRenderPlugin(),  # Primary at /schema
        RedocRenderPlugin(version="2.0.0"),  # ReDoc with fixed version
        StoplightRenderPlugin(),  # Stoplight Elements with defaults
        RapidocRenderPlugin(),  # RapiDoc with defaults
    ],
)

app = Litestar(
    route_handlers=[
        healthz,
        login,
        me,
        logout,
        list_todos_handler,
        create_todo_handler,
        get_todo_handler,
        update_todo_handler,
        delete_todo_handler,
        add_tag_handler,
        get_tags_handler,
        remove_tag_handler,
        get_todos_by_tag_handler,
    ],
    stores={"sessions": session_store},
    middleware=[session_mw],
    debug=True,
    openapi_config=openapi_config,
)
