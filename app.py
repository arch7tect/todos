from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any  # <- added Any
from uuid import uuid4

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

# Async Redis client for app data
redis = aioredis.from_url(REDIS_URL, decode_responses=True)

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
class TodoIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    done: bool = False


@dataclass
class LoginIn:
    name: str


@dataclass
class Todo:
    id: str
    title: str
    done: bool = False

    @staticmethod
    def key(todo_id: str) -> str:
        return f"{REDIS_NAMESPACE}item:{todo_id}"

    @staticmethod
    def index_key() -> str:
        return f"{REDIS_NAMESPACE}index"

    def dumps(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def loads(s: str) -> "Todo":
        data: dict[str, Any] = json.loads(s)
        return Todo(**data)


# --- data helpers (Redis persistence) ---
async def save_todo(todo: Todo) -> None:
    pipe = redis.pipeline()
    _ = pipe.sadd(Todo.index_key(), todo.id)
    _ = pipe.set(Todo.key(todo.id), todo.dumps())
    _ = await pipe.execute()


async def get_todo(todo_id: str) -> Todo | None:
    data = await redis.get(Todo.key(todo_id))
    return Todo.loads(data) if data else None


async def delete_todo(todo_id: str) -> None:
    pipe = redis.pipeline()
    _ = pipe.srem(Todo.index_key(), todo_id)
    _ = pipe.delete(Todo.key(todo_id))
    _ = await pipe.execute()


async def list_todos(limit: int = 500) -> list[Todo]:
    items: list[Todo] = []
    cursor = 0
    ids: list[str] = []
    while True:
        cursor, batch = await redis.sscan(Todo.index_key(), cursor=cursor, count=256)
        ids.extend(batch)
        if cursor == 0 or len(ids) >= limit:
            break
    if not ids:
        return []
    values = await redis.mget([Todo.key(tid) for tid in ids[:limit]])
    for v in values:
        if v:
            items.append(Todo.loads(v))
    return items


# --- routes ---
@get("/healthz")
async def healthz() -> dict[str, Any]:
    ok = await redis.ping()
    return {"ok": bool(ok)}


@post("/login", status_code=HTTP_201_CREATED)
async def login(data: LoginIn, request: Any) -> dict[str, Any]:  # <- annotated
    user = data.name.strip()
    if not user:
        return {"error": "user is required"}
    request.session["user"] = user
    return {"logged_in_as": user}


@get("/me", status_code=HTTP_200_OK)
async def me(request: Any) -> dict:  # <- annotated
    return {"user": request.session.get("user")}


@delete("/logout", status_code=HTTP_204_NO_CONTENT)
async def logout(request: Any) -> Response[None]:  # <- annotated
    request.session.clear()
    return Response(None, status_code=HTTP_204_NO_CONTENT)


@get("/todos")
async def list_todos_handler() -> list[Todo]:
    return await list_todos()


@post("/todos", status_code=HTTP_201_CREATED)
async def create_todo_handler(data: TodoIn) -> Todo:
    todo = Todo(id=str(uuid4()), title=data.title, done=data.done)
    await save_todo(todo)
    return todo


@get("/todos/{todo_id:str}")
async def get_todo_handler(todo_id: str) -> Todo | Response[None]:
    todo = await get_todo(todo_id)
    return todo if todo else Response(content=None, status_code=HTTP_404_NOT_FOUND)


@put("/todos/{todo_id:str}")
async def update_todo_handler(todo_id: str, data: TodoIn) -> Todo | Response[None]:
    todo = await get_todo(todo_id)
    if not todo:
        return Response(content=None, status_code=HTTP_404_NOT_FOUND)
    todo.title = data.title
    todo.done = data.done
    await save_todo(todo)
    return todo


@delete("/todos/{todo_id:str}", status_code=HTTP_204_NO_CONTENT)
async def delete_todo_handler(todo_id: str) -> Response[None]:
    await delete_todo(todo_id)
    return Response(content=None, status_code=HTTP_204_NO_CONTENT)


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
    ],
    stores={"sessions": session_store},
    middleware=[session_mw],
    debug=True,
    openapi_config=openapi_config,
)
