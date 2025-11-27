"""
Integration tests for the Todo API.

These tests require the API server to be running on localhost:8000.
Run the tests with: uv run pytest test_integration.py -v
"""

import httpx
import pytest


class TestTodoAPI:
    """Integration tests for the Todo API."""

    BASE_URL = "http://localhost:8000"

    @pytest.fixture
    def client(self):
        """Create an HTTP client for testing."""
        return httpx.Client(base_url=self.BASE_URL)

    @pytest.fixture
    def authenticated_client(self, client):
        """Create an authenticated HTTP client with a session."""
        # Login to get a session
        response = client.post("/login", json={"name": "testuser"})
        assert response.status_code == 201  # Login returns 201 Created
        assert response.json() == {"name": "testuser"}
        return client

    def test_health_check(self, client):
        """Test the health check endpoint."""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    def test_me_endpoint_without_session(self, client):
        """Test /me endpoint when not logged in."""
        response = client.get("/me")
        assert response.status_code == 200
        assert response.json() == {"name": ""}

    def test_login_endpoint(self, client):
        """Test the login endpoint."""
        response = client.post("/login", json={"name": "integrationtest"})
        assert response.status_code == 201  # Login returns 201 Created
        assert response.json() == {"name": "integrationtest"}

    def test_me_endpoint_with_session(self, authenticated_client):
        """Test /me endpoint when logged in."""
        response = authenticated_client.get("/me")
        assert response.status_code == 200
        assert response.json() == {"name": "testuser"}

    def test_logout_endpoint(self, authenticated_client):
        """Test the logout endpoint."""
        # First verify we're logged in
        response = authenticated_client.get("/me")
        assert response.json() == {"name": "testuser"}

        # Logout
        response = authenticated_client.delete("/logout")
        assert response.status_code == 204  # Logout returns 204 No Content

        # Verify we're logged out
        response = authenticated_client.get("/me")
        assert response.json() == {"name": ""}

    def test_list_todos_empty(self, authenticated_client):
        """Test listing todos when there are none."""
        # Clear any existing todos first by getting the list and deleting each one
        response = authenticated_client.get("/todos")
        todos = response.json()
        for todo in todos:
            authenticated_client.delete(f"/todos/{todo['id']}")

        # Now test empty list
        response = authenticated_client.get("/todos")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_todo(self, authenticated_client):
        """Test creating a new todo."""
        todo_data = {"title": "Integration test todo", "done": False}
        response = authenticated_client.post("/todos", json=todo_data)

        assert response.status_code == 201
        created_todo = response.json()
        assert "id" in created_todo
        assert created_todo["title"] == "Integration test todo"
        assert created_todo["done"] is False

        # Clean up
        authenticated_client.delete(f"/todos/{created_todo['id']}")

    def test_get_todo_by_id(self, authenticated_client):
        """Test getting a specific todo by ID."""
        # Create a todo first
        todo_data = {"title": "Test get by ID", "done": False}
        create_response = authenticated_client.post("/todos", json=todo_data)
        created_todo = create_response.json()
        todo_id = created_todo["id"]

        # Get the todo by ID
        response = authenticated_client.get(f"/todos/{todo_id}")
        assert response.status_code == 200
        retrieved_todo = response.json()
        assert retrieved_todo == created_todo

        # Clean up
        authenticated_client.delete(f"/todos/{todo_id}")

    def test_get_nonexistent_todo(self, authenticated_client):
        """Test getting a todo that doesn't exist."""
        fake_id = "nonexistent-todo-id"
        response = authenticated_client.get(f"/todos/{fake_id}")
        assert response.status_code == 404

    def test_update_todo(self, authenticated_client):
        """Test updating an existing todo."""
        # Create a todo first
        todo_data = {"title": "Original title", "done": False}
        create_response = authenticated_client.post("/todos", json=todo_data)
        created_todo = create_response.json()
        todo_id = created_todo["id"]

        # Update the todo
        update_data = {"title": "Updated title", "done": True}
        response = authenticated_client.put(f"/todos/{todo_id}", json=update_data)
        assert response.status_code == 200
        updated_todo = response.json()
        assert updated_todo["id"] == todo_id
        assert updated_todo["title"] == "Updated title"
        assert updated_todo["done"] is True

        # Verify the update persisted
        get_response = authenticated_client.get(f"/todos/{todo_id}")
        assert get_response.json() == updated_todo

        # Clean up
        authenticated_client.delete(f"/todos/{todo_id}")

    def test_update_nonexistent_todo(self, authenticated_client):
        """Test updating a todo that doesn't exist."""
        fake_id = "nonexistent-todo-id"
        update_data = {"title": "Updated title", "done": True}
        response = authenticated_client.put(f"/todos/{fake_id}", json=update_data)
        assert response.status_code == 404

    def test_delete_todo(self, authenticated_client):
        """Test deleting a todo."""
        # Create a todo first
        todo_data = {"title": "To be deleted", "done": False}
        create_response = authenticated_client.post("/todos", json=todo_data)
        created_todo = create_response.json()
        todo_id = created_todo["id"]

        # Delete the todo
        response = authenticated_client.delete(f"/todos/{todo_id}")
        assert response.status_code == 204

        # Verify the todo is deleted
        get_response = authenticated_client.get(f"/todos/{todo_id}")
        assert get_response.status_code == 404

    def test_tag_flow(self, authenticated_client):
        """Test adding tags to a todo and fetching by tag."""
        # Create a todo
        todo_data = {"title": "Tag test todo", "done": False}
        create_resp = authenticated_client.post("/todos", json=todo_data)
        assert create_resp.status_code == 201
        todo = create_resp.json()
        todo_id = todo["id"]

        # Initially, todo should have empty tags list
        assert "tags" in todo
        assert todo["tags"] == []

        # Add a tag
        tag_resp = authenticated_client.post(f"/todos/{todo_id}/tags", json={"tag": "urgent"})
        assert tag_resp.status_code == 201

        # Get todo by ID - should now include tags
        get_resp = authenticated_client.get(f"/todos/{todo_id}")
        assert get_resp.status_code == 200
        todo_with_tags = get_resp.json()
        assert "tags" in todo_with_tags
        assert "urgent" in todo_with_tags["tags"]

        # Retrieve tags for todo (legacy endpoint still works)
        tags_resp = authenticated_client.get(f"/todos/{todo_id}/tags")
        assert tags_resp.status_code == 200
        assert "urgent" in tags_resp.json()

        # Add another tag
        tag_resp2 = authenticated_client.post(f"/todos/{todo_id}/tags", json={"tag": "work"})
        assert tag_resp2.status_code == 201

        # List all todos - should include tags
        list_resp = authenticated_client.get("/todos")
        assert list_resp.status_code == 200
        todos = list_resp.json()
        found_todo = next((t for t in todos if t["id"] == todo_id), None)
        assert found_todo is not None
        assert "tags" in found_todo
        assert "urgent" in found_todo["tags"]
        assert "work" in found_todo["tags"]

        # Retrieve todos by tag - should include all tags
        by_tag_resp = authenticated_client.get("/tags/urgent/todos")
        assert by_tag_resp.status_code == 200
        tagged_todos = by_tag_resp.json()
        found = next((t for t in tagged_todos if t["id"] == todo_id), None)
        assert found is not None
        assert "tags" in found
        assert "urgent" in found["tags"]
        assert "work" in found["tags"]

        # Clean up
        authenticated_client.delete(f"/todos/{todo_id}")

    def test_todo_json_round_trip(self, authenticated_client):
        """Ensure todos persist and return JSON-friendly types (no bytes) after round trips."""
        # Create a todo and add tags
        todo_data = {"title": "JSON round trip", "done": False}
        create_resp = authenticated_client.post("/todos", json=todo_data)
        assert create_resp.status_code == 201
        todo_id = create_resp.json()["id"]

        authenticated_client.post(f"/todos/{todo_id}/tags", json={"tag": "alpha"})
        authenticated_client.post(f"/todos/{todo_id}/tags", json={"tag": "beta"})

        # Fetch by ID and ensure fields are proper JSON types
        get_resp = authenticated_client.get(f"/todos/{todo_id}")
        assert get_resp.status_code == 200
        todo = get_resp.json()
        assert isinstance(todo["id"], str)
        assert isinstance(todo["title"], str)
        assert isinstance(todo["done"], bool)
        assert all(isinstance(tag, str) for tag in todo.get("tags", []))
        assert set(todo["tags"]) == {"alpha", "beta"}

        # List todos and confirm same constraints hold
        list_resp = authenticated_client.get("/todos")
        assert list_resp.status_code == 200
        todos = list_resp.json()
        listed = next(t for t in todos if t["id"] == todo_id)
        assert isinstance(listed["id"], str)
        assert isinstance(listed["title"], str)
        assert isinstance(listed["done"], bool)
        assert all(isinstance(tag, str) for tag in listed.get("tags", []))
        assert set(listed["tags"]) == {"alpha", "beta"}

        # Clean up
        authenticated_client.delete(f"/todos/{todo_id}")


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
