import asyncio
from pathlib import Path
from uuid import UUID

lazy from jinja2 import StrictUndefined, TemplateError
lazy from jinja2.sandbox import SandboxedEnvironment

from app_foundation.documents import DocumentContext, DocumentTemplate
from app_foundation.primitives import InfrastructureUnavailable, NotFound, ValidationError


class HtmlDocumentRenderer:
    async def render(self, template: DocumentTemplate, context: DocumentContext) -> bytes:
        if template.content_type != "text/html":
            raise ValidationError("HTML renderer requires an HTML template")
        try:
            environment = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)
            return environment.from_string(template.source).render(dict(context.values)).encode()
        except TemplateError as error:
            raise ValidationError("Document template failed") from error


class FileDocumentStorage:
    """The root must be private to the application, never writable by untrusted users."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        try:
            canonical = str(UUID(key))
        except ValueError as error:
            raise ValidationError("Document keys must be canonical UUIDs") from error
        if canonical != key:
            raise ValidationError("Document keys must be canonical UUIDs")
        path = self._root / key
        if path.is_symlink() or path.resolve().parent != self._root:
            raise ValidationError("Unsafe document path")
        return path

    async def put(self, key: str, content: bytes) -> None:
        path = self._path(key)
        try:
            await asyncio.to_thread(self._root.mkdir, parents=True, exist_ok=True, mode=0o700)
            await asyncio.to_thread(self._write, path, content)
        except OSError as error:
            raise InfrastructureUnavailable("Document storage failed") from error

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        with path.open("xb") as output:
            output.write(content)
        path.chmod(0o600)

    async def get(self, key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._path(key).read_bytes)
        except FileNotFoundError as error:
            raise NotFound("Document not found") from error
        except OSError as error:
            raise InfrastructureUnavailable("Document storage failed") from error
