"""
Integration tests for the Todo API.

These tests require the API server to be running on localhost:8000.
Run the tests with: uv run pytest test_integration.py -v
"""

import pytest
import httpx


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
        assert response.json() == {"logged_in_as": "testuser"}
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
        assert response.json() == {"user": None}

    def test_login_endpoint(self, client):
        """Test the login endpoint."""
        response = client.post("/login", json={"name": "integrationtest"})
        assert response.status_code == 201  # Login returns 201 Created
        assert response.json() == {"logged_in_as": "integrationtest"}

    def test_me_endpoint_with_session(self, authenticated_client):
        """Test /me endpoint when logged in."""
        response = authenticated_client.get("/me")
        assert response.status_code == 200
        assert response.json() == {"user": "testuser"}

    def test_logout_endpoint(self, authenticated_client):
        """Test the logout endpoint."""
        # First verify we're logged in
        response = authenticated_client.get("/me")
        assert response.json() == {"user": "testuser"}

        # Logout
        response = authenticated_client.delete("/logout")
        assert response.status_code == 204  # Logout returns 204 No Content

        # Verify we're logged out
        response = authenticated_client.get("/me")
        assert response.json() == {"user": None}

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

    def test_full_crud_workflow(self, authenticated_client):
        """Test a complete CRUD workflow."""
        # Create
        todo_data = {"title": "CRUD workflow test", "done": False}
        create_response = authenticated_client.post("/todos", json=todo_data)
        assert create_response.status_code == 201
        todo = create_response.json()
        todo_id = todo["id"]

        # Read (list)
        list_response = authenticated_client.get("/todos")
        assert create_response.status_code == 201
        todos = list_response.json()
        assert any(t["id"] == todo_id for t in todos)

        # Read (by ID)
        get_response = authenticated_client.get(f"/todos/{todo_id}")
        assert get_response.status_code == 200
        assert get_response.json() == todo

        # Update
        update_data = {"title": "Updated CRUD test", "done": True}
        update_response = authenticated_client.put(f"/todos/{todo_id}", json=update_data)
        assert update_response.status_code == 200
        updated_todo = update_response.json()
        assert updated_todo["title"] == "Updated CRUD test"
        assert updated_todo["done"] is True

        # Delete
        delete_response = authenticated_client.delete(f"/todos/{todo_id}")
        assert delete_response.status_code == 204

        # Verify deletion
        get_after_delete = authenticated_client.get(f"/todos/{todo_id}")
        assert get_after_delete.status_code == 404


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])