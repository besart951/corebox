# app-foundation

A typed Python application foundation for independently deployed customer applications.
Install one distribution, select the capabilities you need, and compose dependencies explicitly.
Customer business concepts belong in the consuming application.

This repository implements the accompanying master prompt. Start with the [example consumer](examples/example_app/main.py), [capability map](docs/capabilities.md), and [complete file tree](docs/tree.md).
The software is proprietary; distribution requires a separate agreement with its owner.

## Requirements and installation

- Python **3.15+**, PostgreSQL, and uv. Development was validated with Python 3.15.0rc3.
- The library uses FastAPI, typed async SQLAlchemy 2.1, Alembic, Pydantic v2, Argon2, PyJWT, and cryptography.
- Development tools are uv, Ruff, ty, pytest, pytest-asyncio, and httpx.

```bash
uv add app-foundation
uv add "app-foundation[postgres,google,stripe]"
```

The base package contains all domain modules and the HTTP/SQLAlchemy integration code. PostgreSQL drivers and provider integrations are extras:

| Extra | Dependency/capability |
| --- | --- |
| `postgres` | psycopg 3 |
| `google` | google-auth, requests, httpx |
| `stripe` | Stripe SDK, httpx |
| `smtp` or `email` | aiosmtplib |
| `whatsapp` | httpx; Meta Graph API adapter |
| `documents` | Jinja2 HTML rendering |
| `realtime` | SSE/WebSocket integration, no additional dependency |
| `all` | All supported adapters |

Feature roots never import provider SDKs. Selected provider adapters use Python 3.15 lazy imports to defer SDK initialization. No Python 3.14 compatibility layer is included.

## Quick start

```bash
uv sync --all-extras --dev
cp .env.example .env
```

Fill `.env` with your local database password and these values:

```dotenv
FOUNDATION_DATABASE_URL=postgresql+psycopg://foundation:YOUR_PASSWORD@localhost:5432/foundation
EXAMPLE_DATABASE_URL=postgresql+psycopg://foundation:YOUR_PASSWORD@localhost:5432/foundation
```

Generate an independent JWT secret and Fernet encryption key, then put them into `EXAMPLE_JWT_SECRET` and `EXAMPLE_ENCRYPTION_KEY`:

```bash
uv run python -c 'import secrets; print(secrets.token_urlsafe(48))'
uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

```bash
docker compose up -d --wait
uv run --env-file .env alembic upgrade heads
uv run fastapi dev examples/example_app/dev.py
# Equivalent factory entrypoint:
uv run uvicorn examples.example_app.main:create_app --factory
```

Visit `/docs` and `/health`. The example seeds application-owned roles during startup. Registration queues a verification email; verify the token before password login. Configure SMTP for actual delivery. Without SMTP the example deliberately uses an in-memory email sender and sends nothing externally. Verification links target a consuming frontend, which submits the token to the corresponding POST endpoint; this repository does not implement a frontend.

The example has its own `pyproject.toml` showing a local path dependency. Published consumers replace that source with their registry dependency. Example code is excluded from the wheel.

## Architecture and transactions

```text
consumer composition
  ├── HTTP routers / jobs / webhooks
  └── application services and immutable domain values
        └── feature-specific Protocol interfaces
              ├── SQLAlchemy / memory repositories
              └── external provider adapters
```

Adapters depend on domain interfaces. Domain code does not import FastAPI, SQLAlchemy, settings, or vendor SDKs. Each feature exports a small explicit public interface:

```python
from app_foundation.identity import User, UserService
from app_foundation.auth import AuthService
from app_foundation.access_control import Authorizer
```

Construct services with explicit dependencies. SQLAlchemy repositories receive an `AsyncSession`; they flush but never commit. HTTP/job composition owns one transaction per operation. `Transaction` queues in-process events until the database commit succeeds. Audit records and outbound delivery records are written inside the originating transaction.

```python
from app_foundation.events import InProcessEventPublisher
from app_foundation.identity import UserService
from app_foundation.identity.sqlalchemy import SqlAlchemyUserRepository
from app_foundation.persistence import Transaction, create_database
from app_foundation.primitives import SystemClock, UUID7Generator

engine, sessions = create_database(database_url)
async with sessions() as session:
    transaction = Transaction(session, InProcessEventPublisher())
    async with transaction.begin():
        users = UserService(
            SqlAlchemyUserRepository(session), SystemClock(), UUID7Generator(), transaction
        )
        user = await users.create("person@example.com", "Person")
await engine.dispose()
```

Repository adapters translate database errors to foundation exceptions. SQLAlchemy mapped records remain infrastructure details. UUIDv7 identifiers use `NewType` for domain distinction. Timestamps use aware UTC values, with injected clocks in deterministic behavior.

## Tenancy and authorization

Each customer application owns its database. Organizations within that application share `af_` tables. Membership, resource lookups, notifications, reminders, and billing use explicit organization scope. A composite foreign key prevents a membership referencing a team in another organization.

`Authorizer` denies by default. Organization-scoped permissions additionally require active organization membership. Global assignments do not silently become tenant permissions. Consumers define permission strings, roles, and optional policies. The example seeds owner/admin/member/viewer roles and permits users to manage their own profiles. Foundation services are trusted application interfaces; HTTP routers perform authentication and authorization before invoking them.

## Authentication and secrets

- Passwords use Argon2; password credentials are separate from users.
- JWTs require issuer, audience, purpose, expiry, issued-at, not-before, subject, and session ID.
- Access authentication checks persistent session revocation and active-user status.
- Refresh rotation serializes on the session family. Reusing an old token revokes that family.
- **Commit `AuthenticationRejected` refresh results before turning them into an HTTP error.** The provided auth router does this; raising inside the transaction would roll back revocation.
- Verification/reset tokens and refresh tokens are stored as hashes. Email delivery temporarily stores verification tokens encrypted with the application's Fernet key.
- TOTP enrollment requires password reauthentication and code confirmation. Recovery codes are shown once, stored as hashes, and consumed under a row lock. TOTP counters prevent replay.
- OAuth validates state, PKCE, nonce, issuer/audience, and verified email. Store the browser binding in browser session state and return it with the callback. Matching email alone never links accounts; linking requires the initiating authenticated account.
- The PostgreSQL rate limiter commits attempts independently, so a rejected authentication transaction does not erase them. Production applications should additionally enforce ingress/IP rate limits.
- Bearer authentication is demonstrated. If adopting cookies, add Secure/HttpOnly/SameSite cookies and explicit CSRF protection. Never put bearer tokens in realtime URLs.
- Keep Fernet keys stable across restarts and back them up securely. Re-encrypt existing encrypted fields before retiring a key. JWT secret rotation invalidates existing access tokens.

Configuration reads are confined to composition and adapters. There are no usable default secrets. Do not enable SQL parameter echo or request-body/access logging that exposes credentials or verification URLs. `ContextFilter` adds correlation context and redacts configured secret values and common credential fields.

## Database migrations

Canonical, immutable revisions are packaged under `app_foundation.persistence.migrations.versions`. Apply migrations explicitly during deployment; startup never creates or silently upgrades tables.

```bash
uv run --env-file .env alembic upgrade heads
uv run --env-file .env alembic current
uv run --env-file .env alembic check
```

A consumer integrates foundation revisions with its own Alembic branch by setting version locations **before** constructing `ScriptDirectory` or calling Alembic commands:

```python
import os
from alembic import command
from alembic.config import Config
from app_foundation.persistence import migration_location

config = Config("alembic.ini")
config.set_main_option("path_separator", "os")
config.set_main_option(
    "version_locations",
    os.pathsep.join((str(migration_location()), "migrations/versions")),
)
command.upgrade(config, "heads")
```

Use your own `env.py`, register selected foundation ORM models via `app_foundation.persistence.models`, and combine metadata with your application's tables. Start the application branch from `base` with a distinct branch label; set `depends_on` to the required foundation revision where application foreign keys require it. Never copy foundation SQL or edit published revisions. The provided root environment is for this repository's foundation branch.

A foundation update can introduce a migration. Review it, back up data, run migration tests, and apply the consumer's combined `heads` before enabling new behavior. Initial installation creates all foundation tables; selecting runtime modules remains independent of schema installation.

## Routers and provider setup

Router factories accept explicit operation scopes and authentication/authorization callbacks. Include only the routers the application exposes. Schemas validate HTTP input, and responses never expose ORM records or password credentials. See the example composition for users, organizations, teams, auth/MFA, notifications, and optional billing/OAuth.

Provider configuration:

- **SMTP:** `EmailSettings` supports host, port, username/password, STARTTLS and implicit TLS. The transport supports plain/HTML bodies, CC/BCC, reply-to, attachments, and message metadata.
- **Google:** configure client ID/secret and the exact registered redirect URI. The browser callback exchanges its code via the OAuth router. Enable `EXAMPLE_GOOGLE_ENABLED` to mount it.
- **Stripe:** configure API key and endpoint signing secret. Enable `EXAMPLE_STRIPE_ENABLED` and allowlist price IDs. Checkout return URLs are application configuration. Close the adapter's HTTP client when its lifetime ends.
- **WhatsApp:** supply a Meta token, phone number ID, and explicit supported API version. Use approved templates when required by Meta's conversation rules.
- **Documents:** HTML rendering escapes substituted values and rejects missing variables. Templates are application-owned, not arbitrary uploaded code. Filesystem storage uses UUID keys and a private application-owned directory. Renderer and storage are independently replaceable.

Provider tests exercise mappings and error paths through mocked network boundaries. No live paid service or production credential is required by CI.

## Delivery, scheduling, realtime, and audit

Notification preferences apply per user/channel. In-app visibility is independent of persistent outbound delivery records. Database jobs use row locks with `SKIP LOCKED`; failures retry up to five attempts with exponential delays. Delivery is **at least once**: an external send can succeed before the database commit fails. Applications requiring stronger guarantees must use provider idempotency or deduplication.

Verification mail uses a separate encrypted queue. Failed delivery rows remain available for operator inspection; ordinary errors store only safe error classifications. Do not expose these tables through public APIs.

Jobs belong to their features. The scheduler supports interval and five-field cron schedules; its lock interface has memory and PostgreSQL implementations. Missed ticks coalesce, concurrent runs are excluded, and shutdown drains in-flight work. Reminder recurrence supports once/daily/weekly local wall time: ambiguous times use the first occurrence, nonexistent times move forward through the daylight-saving gap, and subsequent occurrences retain that shifted wall time.

The realtime memory broker is bounded and process-local. Slow subscribers disconnect and must reload persistent state. SSE and WebSocket adapters enforce topic access and recheck authorization before each event. They provide no durable replay or cross-process fanout; replace the broker interface when deploying multiple workers that need shared delivery.

Audit records are append-only through the public sink interface and are separate from diagnostic logs. Applications can supply database-role restrictions for stronger tamper resistance. Metrics and tracing are protocols without a vendor dependency. The example records application events into the audit sink within the transaction.

## Tests, typing, and linting

```bash
uv run pytest                         # PostgreSQL tests skip without a test URL
FOUNDATION_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run ruff check --fix .
uv run ruff format .
```

PostgreSQL integration tests use temporary isolated schemas and apply packaged migrations. Unit tests use memory adapters. Architecture tests inspect import direction, exports, forbidden dumping grounds, and module imports. The CI PostgreSQL service ensures integration tests run rather than skip.

All ty diagnostic rules are errors. ORM column declarations use parameterized `MappedColumn[T]` to avoid an implicit `Any` from SQLAlchemy's convenience factory. Ruff allows local exception messages (`TRY003`) and assertions (`S101`); other intentional exceptions carry inline explanations. `py.typed` ships in the wheel.

## Building, releasing, and upgrading

```bash
uv build
uv run python scripts/check_distribution.py
# Supply registry credentials through your environment/secret store:
uv publish --publish-url https://packages.example.com/upload/
```

The distribution check creates a clean temporary environment, installs the built wheel, verifies base-only imports and `py.typed`, checks a typed consumer, installs all extras, and imports every module. Wheels exclude the example and tests; source archives exclude local agent skills.

Version `0.1.0` has one authoritative source in `pyproject.toml`; runtime `__version__` reads installed metadata. Use Semantic Versioning. Before publishing: change the version, update `CHANGELOG.md`, document any public-interface/schema migration, run CI and distribution checks, then tag the matching version. Publishing is an explicit release action, not part of ordinary CI.

Configure a private registry in the consumer without embedding credentials:

```toml
[[tool.uv.index]]
name = "internal"
url = "https://packages.example.com/simple"
explicit = true

[tool.uv.sources]
app-foundation = { index = "internal" }
```

Provide `UV_INDEX_INTERNAL_USERNAME` and `UV_INDEX_INTERNAL_PASSWORD` through the environment or CI secrets. During development, a consumer can instead use `uv add "app-foundation @ git+ssh://git@github.com/besart951/corebox.git@TAG"`.

Consumer lifecycle: foundation change → tests/types/lint → version/tag → build/publish → Renovate or Dependabot dependency-update PR → consumer tests and migration review → merge. Consumers commit `uv.lock` and deliberately upgrade with `uv lock --upgrade-package app-foundation`; they never track unreviewed foundation changes automatically.

## Extending the foundation

Add a feature only for a broadly reusable application concern. Define its values, feature-specific persistence/capability protocols, service, domain exceptions, and explicit exports. Add an adapter and public-behavior tests before adding layers. Persistent features need packaged migrations and PostgreSQL integration tests. Follow the [ADRs](docs/adr/) and architecture tests.

Add a provider by implementing the existing protocol in an adapter namespace, translating errors, validating responses, adding the optional dependency extra, and testing network mappings. Wire it explicitly in consumer composition. There is no plugin discovery or global container.

React/Svelte components and styling belong in a separate frontend package. Backend `Branding` carries only the small set of branding values useful in email and documents.
