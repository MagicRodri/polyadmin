from test_app import client, signed_in


def test_projects_list_hides_inactive_by_default():
    page = client.get("/admin/projects").text
    assert "Apollo" in page and "Cascade" not in page
    assert "Northwind" in page


def test_clients_list():
    page = client.get("/admin/clients").text
    for name in ("Northwind", "Contoso", "Umbrella"):
        assert name in page


def test_project_without_client_renders():
    assert "Fjord" in client.get("/admin/projects?search=Fjord").text
    assert client.get("/admin/projects/6").status_code == 200
    assert client.get("/admin/projects/6/edit").status_code == 200
