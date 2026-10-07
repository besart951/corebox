"""Verify the built artifacts as a consumer outside the checkout."""

import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = """
import importlib
import importlib.resources
import importlib.util
from app_foundation.identity import User, UserService
from app_foundation.auth import AuthService
from app_foundation.access_control import Authorizer
from app_foundation.persistence import migration_location
assert importlib.resources.files("app_foundation").joinpath("py.typed").is_file()
assert list(migration_location().glob("af*.py"))
for feature in (
    "organization", "notification", "billing", "documents", "addresses",
    "scheduling", "jobs", "localization", "realtime", "observability",
):
    importlib.import_module("app_foundation." + feature)
"""


def run(arguments: list[str], cwd: Path) -> None:
    # Fixed executable/argument arrays; never invoke a shell or interpolate user input.
    subprocess.run(arguments, cwd=cwd, check=True)  # noqa: S603


def main() -> None:
    uv = shutil.which("uv")
    assert uv is not None
    wheels = sorted((ROOT / "dist").glob("*.whl"))
    assert len(wheels) == 1, "Build exactly one wheel before checking the distribution"
    wheel = wheels[0]
    archives = tuple((ROOT / "dist").glob("*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0]) as source:
        assert not any("/.agents/" in name for name in source.getnames())
    with ZipFile(wheel) as archive:
        paths = archive.namelist()
        assert "app_foundation/py.typed" in paths
        assert any("migrations/versions/af0001" in path for path in paths)
        assert not any(path.startswith(("tests/", "examples/")) for path in paths)
    with TemporaryDirectory(prefix="foundation-wheel-") as temporary:
        directory = Path(temporary)
        environment = directory / "venv"
        run([uv, "venv", "--python", sys.executable, str(environment)], directory)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([uv, "pip", "install", "--python", str(python), str(wheel)], directory)
        run(
            [
                str(python),
                "-I",
                "-c",
                IMPORTS
                + '\nassert importlib.util.find_spec("stripe") is None\n'
                + 'assert importlib.util.find_spec("aiosmtplib") is None',
            ],
            directory,
        )
        consumer = directory / "consumer.py"
        consumer.write_text(
            "from app_foundation.identity import User\n"
            "from app_foundation.auth import AuthService\n\n"
            "async def user(auth: AuthService, token: str) -> User:\n"
            "    return await auth.authenticate(token)\n"
        )
        run(
            [
                uv,
                "run",
                "--project",
                str(ROOT),
                "ty",
                "check",
                "--python",
                str(python),
                str(consumer),
            ],
            directory,
        )
        run([uv, "pip", "install", "--python", str(python), str(wheel) + "[all]"], directory)
        run(
            [
                str(python),
                "-I",
                "-c",
                IMPORTS
                + "\nimport pkgutil, app_foundation\n"
                + 'prefix = "app_foundation."\n'
                + "for module in pkgutil.walk_packages(app_foundation.__path__, prefix):\n"
                + "    importlib.import_module(module.name)",
            ],
            directory,
        )
        shutil.copytree(
            ROOT / "examples" / "example_app",
            directory / "example_app",
            ignore=shutil.ignore_patterns("__pycache__", ".venv"),
        )
        example = """
from example_app.main import create_app
from example_app.settings import Settings
from cryptography.fernet import Fernet
from pydantic import SecretStr
app = create_app(Settings(
    database_url=SecretStr("postgresql+psycopg://unused/unused"),
    jwt_secret=SecretStr("x" * 40),
    encryption_key=SecretStr(Fernet.generate_key().decode()), jobs_enabled=False,
))
assert "/auth/login" in app.openapi()["paths"]
"""
        run([str(python), "-c", example], directory)
    sys.stdout.write("Wheel verified: base imports, extras, typing, and packaged migrations.\n")


if __name__ == "__main__":
    main()
