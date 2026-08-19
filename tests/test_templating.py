from polyadmin.core.admin import Admin
from polyadmin.core.pagination import paginate
from polyadmin.templating import Renderer
from tests.core.test_model_admin import InMemoryUserAdmin


def make_admin_with_users(*emails):
    user_admin = InMemoryUserAdmin()
    for email in emails:
        user_admin.create({"email": email})
    admin = Admin(model_admins=[user_admin])
    return admin, user_admin


def test_render_list_shows_rows_and_nav():
    admin, user_admin = make_admin_with_users("john@example.com", "mary@example.com")
    page = paginate(user_admin.get_queryset(), page=1, page_size=10)

    html = Renderer().render_list(admin, user_admin, page)

    assert "john@example.com" in html
    assert "mary@example.com" in html
    assert "Email" in html  # column header from the field label
    assert 'href="/admin/users"' in html  # nav item


def test_render_list_shows_empty_state():
    admin, user_admin = make_admin_with_users()
    page = paginate(user_admin.get_queryset(), page=1, page_size=10)

    html = Renderer().render_list(admin, user_admin, page)

    assert "No records." in html


def test_render_list_pagination_links():
    admin, user_admin = make_admin_with_users(*[f"user{i}@example.com" for i in range(15)])
    page = paginate(user_admin.get_queryset(), page=2, page_size=10)

    html = Renderer().render_list(admin, user_admin, page)

    assert "Page 2 of 2" in html
    # page=1 is the implied default, so the first/previous jumps are the
    # bare list URL rather than an explicit page=1.
    assert "page=3" not in html  # no next link on the last page
    assert "Rows per page" in html


def test_render_detail_shows_field_values():
    admin, user_admin = make_admin_with_users("john@example.com")
    user = user_admin.get_queryset()[0]

    html = Renderer().render_detail(admin, user_admin, user)

    assert "john@example.com" in html
    assert "Yes" in html  # is_active defaults to True


def test_render_form_prefills_from_object_on_edit():
    admin, user_admin = make_admin_with_users("john@example.com")
    user = user_admin.get_queryset()[0]

    html = Renderer().render_form(admin, user_admin, obj=user)

    assert 'value="john@example.com"' in html
    assert ">Edit" in html


def test_render_form_shows_field_errors():
    admin, user_admin = make_admin_with_users()

    html = Renderer().render_form(
        admin, user_admin, data={"email": ""}, errors={"email": ["Email is required."]}
    )

    assert "Email is required." in html
    assert ">New</span>" in html


def test_render_delete_confirmation():
    admin, user_admin = make_admin_with_users("john@example.com")
    user = user_admin.get_queryset()[0]

    html = Renderer().render_delete(admin, user_admin, user)

    assert "Are you sure you want to delete this User?" in html


def test_application_override_takes_precedence(tmp_path):
    override_dir = tmp_path / "admin" / "resource"
    override_dir.mkdir(parents=True)
    (override_dir / "list.html").write_text("CUSTOM LIST TEMPLATE")

    admin, user_admin = make_admin_with_users()
    page = paginate(user_admin.get_queryset(), page=1, page_size=10)

    html = Renderer(template_dirs=[tmp_path]).render_list(admin, user_admin, page)

    assert html == "CUSTOM LIST TEMPLATE"


def test_resource_specific_template_beats_generic_default(tmp_path):
    override_dir = tmp_path / "admin" / "resource" / "users"
    override_dir.mkdir(parents=True)
    (override_dir / "list.html").write_text("USERS-ONLY LIST TEMPLATE")

    admin, user_admin = make_admin_with_users()
    page = paginate(user_admin.get_queryset(), page=1, page_size=10)

    html = Renderer(template_dirs=[tmp_path]).render_list(admin, user_admin, page)

    assert html == "USERS-ONLY LIST TEMPLATE"
