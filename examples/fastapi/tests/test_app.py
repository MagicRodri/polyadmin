from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_dashboard_renders_at_admin_root():
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 200
    assert "Overview" in response.text


def test_seeded_users_appear_in_list():
    response = client.get("/admin/users")
    assert response.status_code == 200
    assert "admin@example.com" in response.text
    assert "jane@example.com" in response.text


def test_create_user_end_to_end():
    response = client.post(
        "/admin/users/create",
        data={"email": "new-user@example.com", "is_active": "on"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    location = response.headers["location"]
    detail = client.get(location)
    assert detail.status_code == 200
    assert "new-user@example.com" in detail.text
