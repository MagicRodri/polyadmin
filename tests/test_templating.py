import re

from polyadmin.core.admin import Admin
from polyadmin.core.pagination import paginate
from polyadmin.i18n import GettextTranslator, I18n, use_locale
from polyadmin.templating import FRAMEWORK_TEMPLATES_DIR, Renderer
from tests.core.test_i18n import RU_PLURALS, write_catalog
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


# -- gettext in templates ------------------------------------------------
# `_` and `ngettext` return plain text, so autoescape escapes a translation
# at output like any other string, and `|tojson` serialises the raw text.


def render_in(locale, source, *, tmp_path=None, entries=None, plural_forms=None, **context):
    """Render `source` in `locale`, with an optional host catalog for it."""
    catalogs = []
    if entries:
        catalogs = [(write_catalog(tmp_path, locale, entries, domain="host", plural_forms=plural_forms), "host")]
    translator = GettextTranslator(catalogs)
    i18n = I18n(translator=translator, default="en", supported=sorted({"en", locale}), names={})
    renderer = Renderer(i18n=i18n)
    with use_locale(locale, translator):
        return renderer.env.from_string(source).render(**context)


def test_a_host_string_with_a_percent_sign_renders_as_is():
    # No arguments, no formatting -- as with Go's t.
    assert render_in("en", "{{ _(label) }}", label="Discount (%)") == "Discount (%)"
    assert render_in("en", "{{ _(label) }}", label="100% done") == "100% done"


def test_a_translated_host_string_is_escaped_in_attributes_and_text():
    html = render_in("en", '<p title="{{ _(label) }}">{{ _(label) }}</p>', label='Say "hi" <b>')
    assert html == '<p title="Say &#34;hi&#34; &lt;b&gt;">Say &#34;hi&#34; &lt;b&gt;</p>'


def test_tojson_serialises_the_raw_translation(tmp_path):
    html = render_in("fr", """{{ _("Light mode")|tojson }}""", tmp_path=tmp_path,
                     entries={"Light mode": "Mode d'affichage"})
    assert html == '"Mode d\\u0027affichage"'
    assert "&#39;" not in html


def test_placeholders_are_formatted_and_their_values_escaped(tmp_path):
    html = render_in("fr", """{{ _("Remove %(label)s", label=label) }} {{ _("100%% of %(label)s", label=label) }}""",
                     tmp_path=tmp_path, entries={"Remove %(label)s": "Retirer %(label)s"}, label="<b>")
    assert html == "Retirer &lt;b&gt; 100% of &lt;b&gt;"


def test_ngettext_picks_the_plural_form_and_binds_num(tmp_path):
    entries = {("%(num)d record", "%(num)d records"): ["%(num)d запись", "%(num)d записи", "%(num)d записей"]}
    source = """{% for n in counts %}{{ ngettext("%(num)d record", "%(num)d records", n) }};{% endfor %}"""
    html = render_in("ru", source, tmp_path=tmp_path, entries=entries, plural_forms=RU_PLURALS, counts=[1, 3, 5])
    assert html == "1 запись;3 записи;5 записей;"
    # Further placeholders ride alongside the bound count.
    html = render_in("en", """{{ ngettext("%(n)s of %(num)d row", "%(n)s of %(num)d rows", 3, n="<n>") }}""")
    assert html == "&lt;n&gt; of 3 rows"


def test_marker_fills_use_a_function_replacement():
    """String.replace with a string replacement expands "$&", "$1" and the
    like, so a record label containing "$&" would come out mangled. Every
    client-side fill of a {marker} must pass a function. Mirrors Go's
    TestMarkerFillsUseAFunctionReplacement."""
    fill = re.compile(r"""\.replace\('\{\w+\}',\s*([^,]*?)\)\"""")
    found = []
    for path in FRAMEWORK_TEMPLATES_DIR.rglob("*.html"):
        found += [(path.name, m.group(0), m.group(1).strip()) for m in fill.finditer(path.read_text())]
    assert len(found) >= 2, "the multi-select's and the pagination's fills"
    assert all(replacement.startswith("() =>") for _, _, replacement in found), found
