import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "polyadmin"
CONTRIB = PACKAGE / "contrib"
THIRD_PARTY = ("fastapi", "starlette", "sqlalchemy", "sqlmodel")


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _offending(paths, forbidden):
    found = []
    for path in paths:
        for name in _imports(path):
            if any(name == f or name.startswith(f + ".") for f in forbidden):
                found.append(f"{path.relative_to(PACKAGE.parent)}: {name}")
    return found


def test_core_imports_no_contrib_and_no_framework_or_orm():
    core = [p for p in PACKAGE.rglob("*.py") if CONTRIB not in p.parents]
    assert not _offending(core, ("polyadmin.contrib", *THIRD_PARTY))


def test_sqlalchemy_contrib_does_not_import_the_fastapi_contrib():
    paths = list((CONTRIB / "sqlalchemy").rglob("*.py"))
    assert paths, "polyadmin/contrib/sqlalchemy is missing"
    assert not _offending(paths, ("polyadmin.contrib.fastapi", "fastapi", "starlette"))


def test_the_framework_static_dir_is_still_the_package_root_static():
    import polyadmin
    from polyadmin.contrib.fastapi.static import FRAMEWORK_STATIC_DIR

    assert FRAMEWORK_STATIC_DIR == Path(polyadmin.__file__).resolve().parent / "static"
