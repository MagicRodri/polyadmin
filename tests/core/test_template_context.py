from polyadmin.core.admin import Admin
from polyadmin.core.model_admin import ModelAdmin
from polyadmin.core.pagination import paginate
from polyadmin.core.template_context import GROUP_ICON, build_nav, category_breadcrumb, dashboard_context, list_context


class User:
    def __init__(self, id):
        self.id = id


class UserAdmin(ModelAdmin):
    model = User


class OrganizationAdmin(ModelAdmin):
    model = User
    slug = "organizations"


class HiddenAdmin(ModelAdmin):
    model = User
    slug = "hidden"
    can_view = False


async def _noop_handler(ctx):
    return None


def test_ungrouped_admins_render_flat():
    admin = Admin(model_admins=[UserAdmin()])
    nav = build_nav(admin, "/admin", None)
    assert nav == [
        {
            "type": "link",
            "key": "resource:users",
            "label": "User",
            "url": "/admin/users",
            "icon": "collection",
            "active": False,
        }
    ]


def test_admin_icon_defaults_to_collection():
    assert UserAdmin().icon == "collection"


def test_admin_icon_can_be_overridden():
    class IconedUserAdmin(UserAdmin):
        icon = "table"

    admin = Admin(model_admins=[IconedUserAdmin()])
    nav = build_nav(admin, "/admin", None)
    assert nav[0]["icon"] == "table"


def test_nested_link_keeps_its_own_icon_inside_a_group():
    class GroupedUserAdmin(UserAdmin):
        category = "Directory"
        icon = "table"

    admin = Admin(model_admins=[GroupedUserAdmin()])
    nav = build_nav(admin, "/admin", None)
    assert nav[0]["links"][0]["icon"] == "table"


def test_group_uses_the_fixed_group_icon():
    class GroupedUserAdmin(UserAdmin):
        category = "Directory"

    admin = Admin(model_admins=[GroupedUserAdmin()])
    nav = build_nav(admin, "/admin", None)
    assert nav[0]["icon"] == GROUP_ICON == "folder"


def test_category_breadcrumb_is_empty_for_no_category():
    assert category_breadcrumb(None) == []
    assert category_breadcrumb("") == []


def test_category_breadcrumb_is_a_plain_non_active_non_link_crumb():
    assert category_breadcrumb("Directory") == [{"label": "Directory", "url": None, "active": False}]


def test_list_context_breadcrumbs_include_category_and_mark_active():
    class GroupedUserAdmin(UserAdmin):
        category = "Directory"

    grouped = GroupedUserAdmin()
    admin = Admin(model_admins=[grouped])
    ctx = list_context(admin, grouped, paginate([], page=1, page_size=10))
    assert ctx["breadcrumbs"] == [
        {"label": "Directory", "url": None, "active": False},
        {"label": "User", "url": None, "active": True},
    ]


def test_list_context_breadcrumbs_omit_category_when_unset():
    user_admin = UserAdmin()
    admin = Admin(model_admins=[user_admin])
    ctx = list_context(admin, user_admin, paginate([], page=1, page_size=10))
    assert ctx["breadcrumbs"] == [{"label": "User", "url": None, "active": True}]


def test_dashboard_context_breadcrumb_is_active():
    admin = Admin()
    dashboard = type("Dashboard", (), {"title": "Overview"})()
    ctx = dashboard_context(admin, dashboard, widgets=[])
    assert ctx["breadcrumbs"] == [{"label": "Overview", "url": None, "active": True}]


def test_admins_sharing_a_category_collapse_into_one_group():
    class GroupedUserAdmin(UserAdmin):
        category = "Directory"

    class GroupedOrgAdmin(OrganizationAdmin):
        category = "Directory"

    admin = Admin(model_admins=[GroupedUserAdmin(), GroupedOrgAdmin()])
    nav = build_nav(admin, "/admin", None)
    assert len(nav) == 1
    group = nav[0]
    assert group["type"] == "group"
    assert group["label"] == "Directory"
    assert [link["key"] for link in group["links"]] == ["resource:users", "resource:organizations"]


def test_categories_ordered_by_first_appearance_and_ungrouped_stay_flat():
    class GroupedUserAdmin(UserAdmin):
        category = "Directory"

    admin = Admin(model_admins=[GroupedUserAdmin(), OrganizationAdmin()])
    nav = build_nav(admin, "/admin", None)
    assert [entry["type"] for entry in nav] == ["group", "link"]


def test_group_active_when_it_contains_current_resource():
    class GroupedUserAdmin(UserAdmin):
        category = "Directory"

    admin = Admin(model_admins=[GroupedUserAdmin()])
    nav = build_nav(admin, "/admin", "resource:users")
    assert nav[0]["active"] is True


def test_can_view_false_omits_admin_from_nav():
    admin = Admin(model_admins=[HiddenAdmin()])
    assert build_nav(admin, "/admin", None) == []


def test_pages_join_the_same_grouping_as_model_admins():
    class GroupedUserAdmin(UserAdmin):
        category = "Tools"

    admin = Admin(model_admins=[GroupedUserAdmin()])
    admin.route("/broadcast", _noop_handler, label="Broadcast", category="Tools")
    nav = build_nav(admin, "/admin", None)
    assert len(nav) == 1
    assert [link["key"] for link in nav[0]["links"]] == ["resource:users", "page:/broadcast"]


def test_show_in_nav_false_omits_page():
    admin = Admin()
    admin.route("/hidden", _noop_handler, show_in_nav=False)
    assert build_nav(admin, "/admin", None) == []
