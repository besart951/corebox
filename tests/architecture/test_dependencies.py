import ast
import importlib
import pkgutil
from pathlib import Path

import app_foundation

ROOT = Path(__file__).resolve().parents[2] / "src" / "app_foundation"
ADAPTER_PARTS = {
    "sqlalchemy.py",
    "adapters.py",
    "api.py",
    "api",
    "smtp.py",
    "state.py",
    "rate_limit.py",
    "email.py",
    "providers",
    "google",
    "persistence",
    "config",
    "postgres.py",
    "sse.py",
    "websocket.py",
}
FORBIDDEN = {
    "sqlalchemy",
    "fastapi",
    "stripe",
    "google",
    "psycopg",
    "pydantic_settings",
    "aiosmtplib",
}


def test_domain_dependency_direction() -> None:
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if ADAPTER_PARTS.intersection(relative.parts):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
                if isinstance(node, ast.ImportFrom)
                else []
            )
            for name in names:
                assert name.split(".")[0] not in FORBIDDEN, (relative, name)
                assert not name.startswith("app_foundation.persistence"), (relative, name)
                assert ".sqlalchemy" not in name and ".providers." not in name, (relative, name)


def test_no_dumping_ground_packages_or_wildcard_exports() -> None:
    for path in ROOT.rglob("*"):
        if path.is_dir():
            assert path.name not in {"utils", "helpers", "common", "misc", "managers", "usecases"}
        elif path.suffix == ".py":
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    assert all(alias.name != "*" for alias in node.names), path


def test_import_every_module_without_circular_imports() -> None:
    for module in pkgutil.walk_packages(app_foundation.__path__, app_foundation.__name__ + "."):
        importlib.import_module(module.name)
