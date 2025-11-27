"""
Load test for the Todos API using Locust.

This load test exercises all API endpoints in realistic user scenarios:
- Authentication (login/logout)
- CRUD operations on todos
- Tag management (create, update, query)
- Health checks

Run with:
    # Web UI mode (recommended for interactive testing)
    uv run locust --host http://localhost:8000

    # Headless mode (for CI/CD)
    uv run locust --host http://localhost:8000 --headless -u 10 -r 2 -t 30s

    # Distributed mode (for high load)
    uv run locust --host http://localhost:8000 --master
    uv run locust --host http://localhost:8000 --worker

Arguments:
    -u, --users: Peak number of concurrent users
    -r, --spawn-rate: Users spawned per second
    -t, --run-time: Test duration (e.g., 30s, 5m, 1h)
    --host: Target host URL

Then open http://localhost:8089 to view the dashboard.
"""

import random
from typing import Any

from locust import HttpUser, between, task


class TodoUser(HttpUser):
    """
    Simulates a user interacting with the Todos API.

    Each user:
    1. Logs in to get a session
    2. Performs various todo operations (create, read, update, delete)
    3. Works with tags (add, query, remove)
    4. Periodically checks health
    5. Eventually logs out

    Task weights determine how often each action is performed.
    Higher weight = more frequent execution.
    """

    # Wait 1-3 seconds between tasks to simulate realistic user behavior
    wait_time = between(1, 3)

    def on_start(self):
        """
        Called when a simulated user starts.
        Logs in to establish a session.
        """
        # Generate a unique username for this user
        self.username = f"loadtest_user_{random.randint(1000, 9999)}"

        # Login to get a session cookie
        with self.client.post(
            "/login",
            json={"name": self.username},
            catch_response=True,
            name="/login",
        ) as response:
            if response.status_code == 201:
                response.success()
            else:
                response.failure(f"Login failed with status {response.status_code}")

        # Track todo IDs created by this user for later operations
        self.todo_ids: list[str] = []
        self.tags_used: set[str] = {"urgent", "work", "personal", "shopping", "home"}

    def on_stop(self):
        """
        Called when a simulated user stops.
        Cleans up created todos and logs out.
        """
        # Clean up todos created during the test
        for todo_id in self.todo_ids:
            with self.client.delete(
                f"/todos/{todo_id}",
                catch_response=True,
                name="/todos/{id} [DELETE]",
            ) as response:
                # Don't fail the test if cleanup fails (todo might already be deleted)
                if response.status_code in (204, 404):
                    response.success()

        # Logout
        self.client.delete("/logout", name="/logout")

    @task(1)
    def healthcheck(self):
        """Health check - runs occasionally to ensure service is healthy."""
        with self.client.get("/healthz", catch_response=True) as response:
            if response.status_code == 200 and response.json().get("ok"):
                response.success()
            else:
                response.failure("Health check failed")

    @task(2)
    def check_current_user(self):
        """Verify current user session."""
        with self.client.get("/me", catch_response=True) as response:
            if response.status_code == 200:
                user_data = response.json()
                if user_data.get("name") == self.username:
                    response.success()
                else:
                    response.failure(f"Expected username {self.username}, got {user_data}")
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task(10)
    def create_todo(self):
        """Create a new todo (most frequent operation)."""
        # Randomly decide whether to include tags
        tags = []
        if random.random() > 0.5:  # 50% chance of having tags
            tags = random.sample(list(self.tags_used), k=random.randint(1, 3))

        todo_data = {
            "title": f"Task {random.randint(1, 1000)}: {random.choice(['Review PR', 'Fix bug', 'Write tests', 'Deploy', 'Refactor'])}",
            "done": False,
            "tags": tags,
        }

        with self.client.post(
            "/todos",
            json=todo_data,
            catch_response=True,
            name="/todos [POST]",
        ) as response:
            if response.status_code == 201:
                todo = response.json()
                self.todo_ids.append(todo["id"])
                response.success()
            else:
                response.failure(f"Failed to create todo: {response.status_code}")

    @task(8)
    def list_todos(self):
        """List all todos (frequent operation)."""
        with self.client.get("/todos", catch_response=True, name="/todos [GET]") as response:
            if response.status_code == 200:
                todos = response.json()
                # Optionally validate response structure
                if isinstance(todos, list):
                    response.success()
                else:
                    response.failure("Expected list of todos")
            else:
                response.failure(f"Failed to list todos: {response.status_code}")

    @task(5)
    def get_todo_by_id(self):
        """Get a specific todo by ID."""
        if not self.todo_ids:
            # Skip if no todos created yet
            return

        todo_id = random.choice(self.todo_ids)
        with self.client.get(
            f"/todos/{todo_id}",
            catch_response=True,
            name="/todos/{id} [GET]",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Todo might have been deleted
                self.todo_ids.remove(todo_id)
                response.success()
            else:
                response.failure(f"Failed to get todo: {response.status_code}")

    @task(6)
    def update_todo(self):
        """Update an existing todo."""
        if not self.todo_ids:
            return

        todo_id = random.choice(self.todo_ids)

        # Randomly toggle done status and update title
        update_data = {
            "title": f"Updated: {random.choice(['Complete', 'In Progress', 'Blocked', 'Done'])} - Task {random.randint(1, 100)}",
            "done": random.choice([True, False]),
            "tags": random.sample(list(self.tags_used), k=random.randint(0, 2)),
        }

        with self.client.put(
            f"/todos/{todo_id}",
            json=update_data,
            catch_response=True,
            name="/todos/{id} [PUT]",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Todo was deleted
                self.todo_ids.remove(todo_id)
                response.success()
            else:
                response.failure(f"Failed to update todo: {response.status_code}")

    @task(3)
    def delete_todo(self):
        """Delete a todo."""
        if not self.todo_ids:
            return

        todo_id = random.choice(self.todo_ids)
        self.todo_ids.remove(todo_id)

        with self.client.delete(
            f"/todos/{todo_id}",
            catch_response=True,
            name="/todos/{id} [DELETE]",
        ) as response:
            if response.status_code in (204, 404):
                response.success()
            else:
                response.failure(f"Failed to delete todo: {response.status_code}")

    @task(4)
    def add_tag_to_todo(self):
        """Add a tag to an existing todo."""
        if not self.todo_ids:
            return

        todo_id = random.choice(self.todo_ids)
        tag = random.choice(list(self.tags_used))

        with self.client.post(
            f"/todos/{todo_id}/tags",
            json={"tag": tag},
            catch_response=True,
            name="/todos/{id}/tags [POST]",
        ) as response:
            if response.status_code == 201:
                response.success()
            elif response.status_code == 404:
                # Todo was deleted
                if todo_id in self.todo_ids:
                    self.todo_ids.remove(todo_id)
                response.success()
            else:
                response.failure(f"Failed to add tag: {response.status_code}")

    @task(3)
    def get_tags_for_todo(self):
        """Get all tags for a specific todo."""
        if not self.todo_ids:
            return

        todo_id = random.choice(self.todo_ids)

        with self.client.get(
            f"/todos/{todo_id}/tags",
            catch_response=True,
            name="/todos/{id}/tags [GET]",
        ) as response:
            if response.status_code == 200:
                tags = response.json()
                if isinstance(tags, list):
                    response.success()
                else:
                    response.failure("Expected list of tags")
            else:
                # Accept 404 as success (todo might be deleted)
                response.success()

    @task(2)
    def remove_tag_from_todo(self):
        """Remove a tag from a todo."""
        if not self.todo_ids:
            return

        todo_id = random.choice(self.todo_ids)
        tag = random.choice(list(self.tags_used))

        with self.client.delete(
            f"/todos/{todo_id}/tags/{tag}",
            catch_response=True,
            name="/todos/{id}/tags/{tag} [DELETE]",
        ) as response:
            if response.status_code in (204, 404):
                response.success()
            else:
                response.failure(f"Failed to remove tag: {response.status_code}")

    @task(4)
    def get_todos_by_tag(self):
        """Query todos by tag."""
        tag = random.choice(list(self.tags_used))

        with self.client.get(
            f"/tags/{tag}/todos",
            catch_response=True,
            name="/tags/{tag}/todos [GET]",
        ) as response:
            if response.status_code == 200:
                todos = response.json()
                if isinstance(todos, list):
                    response.success()
                else:
                    response.failure("Expected list of todos")
            else:
                response.failure(f"Failed to query by tag: {response.status_code}")


class QuickSmokeTest(HttpUser):
    """
    Lightweight smoke test user for quick sanity checks.
    Only performs basic operations to verify the API is functional.

    Use this task set for quick validation:
        uv run locust -f locustfile.py QuickSmokeTest --host http://localhost:8000
    """

    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.username = f"smoke_user_{random.randint(1000, 9999)}"
        self.client.post("/login", json={"name": self.username})
        self.todo_id = None

    def on_stop(self):
        if self.todo_id:
            self.client.delete(f"/todos/{self.todo_id}")
        self.client.delete("/logout")

    @task(1)
    def smoke_flow(self):
        """Perform a complete CRUD cycle."""
        # Create
        response = self.client.post(
            "/todos",
            json={"title": "Smoke test", "done": False, "tags": ["test"]},
            name="Smoke: CREATE",
        )
        if response.status_code == 201:
            self.todo_id = response.json()["id"]

            # Read
            self.client.get(f"/todos/{self.todo_id}", name="Smoke: READ")

            # Update
            self.client.put(
                f"/todos/{self.todo_id}",
                json={"title": "Smoke test updated", "done": True, "tags": []},
                name="Smoke: UPDATE",
            )

            # Delete
            self.client.delete(f"/todos/{self.todo_id}", name="Smoke: DELETE")
            self.todo_id = None
