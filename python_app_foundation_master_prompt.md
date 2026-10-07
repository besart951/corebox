# Master Prompt: Reusable Python Application Foundation Package

You are a senior Python software architect and principal backend engineer.

Build a production-grade, reusable Python application foundation that can be installed as a package into many independent customer projects.

The goal is NOT to build one concrete customer application.

The goal is to build a reusable, modular foundation package that provides common application capabilities such as authentication, users, teams, RBAC, notifications, payments, documents, addresses, scheduling, jobs, WhatsApp, localization and realtime updates.

The result must be designed so that:

- many independent applications can install the package;
- applications can use only the modules they need;
- the foundation can evolve independently;
- a new foundation release can be published;
- consuming applications can update to a newer version deliberately;
- breaking changes can be controlled with Semantic Versioning;
- business modules remain independent of infrastructure vendors;
- infrastructure adapters can be replaced without rewriting domain/application logic;
- strict static typing is enforced;
- the package remains easy to understand and maintain.

Do not merely describe the architecture.

CREATE THE COMPLETE PROJECT STRUCTURE AND IMPLEMENT THE FOUNDATION.

---

# 1. Technology baseline

Use:

- Python 3.15+
- FastAPI
- SQLAlchemy 2.x, preferably the latest Python-3.15-compatible SQLAlchemy 2.1 release when available/stable
- Alembic
- Pydantic v2
- pydantic-settings
- PostgreSQL for production
- SQLite only where useful for lightweight tests
- async SQLAlchemy
- psycopg 3 for PostgreSQL
- uv for Python/package/dependency/environment management
- Ruff for linting and formatting
- ty from Astral for static type checking
- pytest
- pytest-asyncio
- httpx for API tests
- argon2 for password hashing
- PyJWT or another small, well-maintained JWT implementation
- cryptography where required
- standard-library-first approach

Do not use Poetry.

Do not use pip-tools.

Do not use Black.

Do not use Flake8.

Do not use mypy unless a dependency absolutely requires it.

The primary developer tooling must be the Astral ecosystem:

- uv
- Ruff
- ty

Use `pyproject.toml` as the central project configuration.

Use a `src/` layout.

The project must be buildable with:

```bash
uv build
```

It must be installable in another project as a normal Python package.

---

# 2. Python 3.15

Target Python 3.15 explicitly.

Use modern Python 3.15 syntax and standard-library capabilities where they improve the architecture.

Use explicit lazy imports from Python 3.15 / PEP 810 where they provide an actual startup-time or optional-dependency benefit.

Example syntax:

```python
lazy import some_heavy_module
lazy from some_package import SomeType
```

Do NOT use lazy imports blindly.

Use them mainly for:

- optional infrastructure adapters;
- heavy third-party integrations;
- provider SDKs;
- modules not required during normal startup;
- optional FastAPI integrations where appropriate.

Do not hide architectural problems behind lazy imports.

Prefer normal imports for core domain and application code.

Do not use compatibility hacks for Python 3.14 or older.

Set:

```toml
requires-python = ">=3.15"
```

If Python 3.15 is still a prerelease in the current environment, configure uv appropriately for prerelease Python/dependencies without weakening the final package requirement.

---

# 3. Package goal

Name the example package:

```text
app-foundation
```

Python import namespace:

```python
app_foundation
```

The package is a reusable application foundation.

A consuming application should eventually be able to do things such as:

```python
from app_foundation.identity import User
from app_foundation.auth import AuthService
from app_foundation.access_control import Authorizer
```

But infrastructure should remain replaceable.

For example, the billing domain must not depend directly on Stripe.

The notification domain must not depend directly on SMTP, Twilio, Meta or another provider.

Authentication must not depend directly on Google.

---

# 4. Architectural style

Use a pragmatic combination of:

- modular monolith;
- feature-based architecture;
- dependency inversion;
- ports and adapters;
- domain/application separation;
- composition over inheritance;
- explicit dependency injection;
- immutable domain objects where practical;
- Protocol-based interfaces;
- no service locator;
- no global mutable container;
- minimal shared kernel;
- high cohesion;
- low coupling.

Do NOT create unnecessary enterprise ceremony.

Do NOT create directories named:

```text
usecases/
utils/
helpers/
common/
misc/
managers/
```

unless there is an extremely specific reason.

Avoid generic dumping grounds.

Do not create one generic `BaseRepository` abstraction for every repository.

Do not create giant god services.

Do not use inheritance merely to share implementation.

Prefer composition and protocols.

---

# 5. Preferred module layout

Use a top-level structure similar to:

```text
app-foundation/
├── pyproject.toml
├── uv.lock
├── README.md
├── LICENSE
├── CHANGELOG.md
├── Makefile
├── .python-version
├── .gitignore
├── src/
│   └── app_foundation/
│       ├── __init__.py
│       ├── py.typed
│       │
│       ├── identity/
│       ├── organization/
│       ├── access_control/
│       ├── auth/
│       ├── notification/
│       ├── communication/
│       ├── billing/
│       ├── documents/
│       ├── addresses/
│       ├── scheduling/
│       ├── jobs/
│       ├── localization/
│       ├── realtime/
│       ├── events/
│       ├── persistence/
│       ├── api/
│       ├── config/
│       └── observability/
│
├── migrations/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── architecture/
└── examples/
    └── example_app/
```

Do not blindly create every possible file.

Create only files with a clear responsibility.

---

# 6. Internal feature structure

Each business feature should be self-contained.

Use a structure similar to this where appropriate:

```text
identity/
├── __init__.py
├── models.py
├── protocols.py
├── repository.py
├── service.py
├── events.py
├── errors.py
├── schemas.py
├── api.py
└── sqlalchemy/
    ├── models.py
    └── repository.py
```

However, adapt this structure when a feature does not need every layer.

The important separation is:

```text
domain/application concepts
        ↓
Protocols / ports
        ↓
infrastructure adapters
```

The inner module must not import its concrete infrastructure adapter.

Example:

```python
class UserRepository(Protocol):
    async def get_by_id(
        self,
        user_id: UserId,
    ) -> User | None: ...

    async def save(
        self,
        user: User,
    ) -> None: ...
```

The SQLAlchemy implementation may depend on the protocol/domain.

The protocol/domain must never depend on SQLAlchemy.

---

# 7. Naming conventions

Use explicit names.

Prefer:

```text
UserRepository
PasswordHasher
TokenIssuer
EmailSender
PaymentProvider
DocumentRenderer
EventPublisher
Clock
IdGenerator
```

Avoid vague names such as:

```text
Manager
Helper
Util
CommonService
BaseService
Processor
Thing
```

unless the domain truly uses such a term.

---

# 8. Strict typing rules

Treat strict typing as a first-class architectural requirement.

Use `ty` as the primary type checker.

Configure ty to be as strict as practically possible.

Code must not rely on:

- implicit `Any`;
- untyped public functions;
- unexplained casts;
- ignored type errors;
- dictionaries with unknown shapes when a typed model is appropriate.

All public functions, methods and attributes must be typed.

Prefer:

- `Protocol`
- `TypeAlias`
- `NewType` or strongly typed value objects where useful
- `Literal`
- generics
- `Self`
- type parameter syntax supported by modern Python
- structural typing
- exhaustive pattern matching where appropriate

Use modern generic syntax instead of legacy `TypeVar` boilerplate where Python 3.15 supports it cleanly.

Example:

```python
class Repository[T](Protocol):
    async def get(self, id: str) -> T | None: ...
```

Do not introduce generics where they make the code less understandable.

Use domain-specific repository protocols instead of one universal generic repository.

---

# 9. Immutability

Prefer immutable values.

Use:

```python
@dataclass(frozen=True, slots=True)
```

for simple immutable domain values when suitable.

Use frozen Pydantic models where the value is a validation/data-transfer object and Pydantic is actually useful.

Do not mutate function input parameters.

Do not expose mutable internal collections unnecessarily.

Prefer tuples/frozensets for domain values that should not change.

State changes should be explicit.

For aggregates where mutation is needed, prefer methods that preserve invariants.

Do not turn every object into a frozen dataclass if it makes persistence or domain logic unnatural.

---

# 10. Error handling

Create domain-specific exceptions.

Examples:

```text
UserNotFound
EmailAlreadyExists
InvalidCredentials
PermissionDenied
TeamNotFound
SubscriptionNotFound
UnsupportedPaymentProvider
```

Do not leak:

- SQLAlchemy exceptions;
- psycopg exceptions;
- Stripe exceptions;
- SMTP exceptions;

through public domain/application APIs.

Translate infrastructure errors at adapter boundaries.

FastAPI exception handlers may translate application/domain errors into HTTP responses.

The domain must never know about HTTP status codes.

---

# 11. Core features to implement

Implement the following modules.

---

## 11.1 Identity / User

Provide:

- User ID
- email
- display name
- first name
- last name
- preferred locale
- timezone
- active/inactive status
- created timestamp
- updated timestamp
- basic profile metadata

Implement:

```text
User
UserRepository
UserService
```

Responsibilities:

- create user;
- retrieve user;
- update basic profile;
- deactivate user;
- normalize email;
- enforce unique email.

Do not put authentication credentials directly into the core User entity.

---

## 11.2 Organization / Team / Group

Implement:

```text
Organization
Team
Membership
```

Support:

- organization membership;
- team membership;
- groups if required;
- owners/admins/members/viewers;
- membership state;
- invitations.

Keep organizational membership separate from authentication.

Use explicit IDs:

```text
OrganizationId
TeamId
MembershipId
```

---

## 11.3 Access Control / RBAC

Implement a reusable authorization module.

Concepts:

```text
Role
Permission
RoleAssignment
Policy
Authorizer
```

Allow permissions such as:

```text
user.read
user.write
team.read
team.write
billing.read
billing.manage
```

Do not hard-code application-specific permissions into the foundation.

Allow consuming applications to define their own permission strings/types.

Provide an API such as:

```python
await authorizer.require(
    principal,
    permission,
    resource,
)
```

Support tenant/organization scope.

Do not mix RBAC directly into FastAPI.

Provide FastAPI adapters/dependencies separately.

---

## 11.4 Authentication

Implement:

- email/password authentication;
- password hashing;
- JWT access tokens;
- refresh tokens;
- refresh-token rotation;
- token revocation;
- email verification;
- password reset;
- session concept where useful.

Ports:

```text
PasswordHasher
TokenIssuer
SessionRepository
VerificationTokenRepository
```

Use Argon2 for passwords.

Security-sensitive values must never be logged.

Do not place Google-specific code in the core auth module.

---

## 11.5 Google OAuth

Create Google OAuth as an adapter/provider.

Core protocol:

```python
class OAuthProvider(Protocol):
    def authorization_url(...): ...
    async def authenticate(...): ...
```

Adapter:

```text
auth/oauth/google/
```

The Google adapter may depend on Google's OAuth libraries.

The rest of the auth module must not.

Design this so Microsoft/GitHub/etc. can later be added without modifying auth business logic.

---

## 11.6 MFA / 2FA

Implement:

- TOTP;
- recovery codes;
- MFA enrollment;
- MFA verification;
- MFA disable flow.

Design with protocols so additional factors can be introduced later.

Never store recovery codes or secrets in plaintext when avoidable.

---

## 11.7 E-mail communication

Separate low-level communication from notifications.

Create:

```text
communication/email/
```

Domain-neutral concepts:

```text
EmailAddress
EmailMessage
EmailAttachment
EmailSender
```

Support:

- HTML body;
- text body;
- CC/BCC;
- attachments;
- reply-to;
- metadata.

Provide at least:

```text
SMTP adapter
in-memory testing adapter
```

Make external services optional adapters.

---

## 11.8 Notification system

Create:

```text
notification/
```

Concepts:

```text
Notification
NotificationChannel
NotificationRecipient
NotificationPreference
NotificationService
NotificationRepository
```

Channels:

- in-app;
- email;
- WhatsApp interface.

The notification module decides WHAT should be communicated.

Communication adapters decide HOW it is transported.

Support notification preferences per user.

---

## 11.9 System notifications

Provide persistent in-app notifications.

Features:

- create;
- unread/read;
- mark one read;
- mark all read;
- notification type;
- link/action metadata;
- created timestamp.

Expose realtime publication hooks for newly created notifications.

---

## 11.10 Billing / Stripe

Core billing concepts:

```text
Customer
Product
Price
Subscription
InvoiceReference
CheckoutSession
PaymentProvider
```

Core billing must not import Stripe.

Create:

```text
billing/providers/stripe/
```

The Stripe adapter implements `PaymentProvider`.

Support:

- create customer;
- checkout session;
- subscription creation;
- cancellation;
- subscription state;
- webhook verification;
- webhook event processing.

Keep external Stripe IDs clearly separated from internal IDs.

Webhook processing must be idempotent.

---

## 11.11 Documents

Create a document module capable of generating documents from user/application data.

Concepts:

```text
DocumentTemplate
DocumentContext
DocumentRenderer
DocumentStorage
GeneratedDocument
```

Do not hard-code one PDF engine into the domain.

Adapters may later support:

- HTML templates;
- PDF;
- DOCX;
- external render service.

Provide a minimal initial implementation.

Keep template rendering separate from storage.

---

## 11.12 Addresses

Create reusable address models.

Support:

```text
Address
PostalAddress
CountryCode
```

Fields may include:

- organization/person;
- street;
- house number;
- additional line;
- postal code;
- city;
- region/state;
- country;
- latitude/longitude optionally.

Keep address normalization and validation behind protocols.

Do not depend permanently on one geocoding provider.

---

## 11.13 Calendar / Reminder

Create:

```text
CalendarEvent
Reminder
ReminderRepository
ReminderService
```

Support:

- due datetime;
- timezone;
- recurring reminders where practical;
- status;
- associated entity reference;
- title;
- description;
- reminder trigger.

Do not couple this directly to Google Calendar.

External calendars should be adapters.

---

## 11.14 Jobs / Cron

Create a generic job abstraction.

Example:

```python
class Job(Protocol):
    @property
    def name(self) -> str: ...

    async def run(self) -> None: ...
```

Create:

```text
Job
JobRegistry
JobRunner
Scheduler
```

Business jobs live in their owning feature.

Example:

```text
auth/jobs/delete_expired_sessions.py
notification/jobs/send_pending_notifications.py
billing/jobs/sync_subscriptions.py
```

The scheduler infrastructure lives in `jobs`.

Do not place business logic inside scheduler configuration.

Support graceful shutdown.

Prevent duplicate execution where relevant.

Make distributed locking replaceable through a protocol.

---

## 11.15 WhatsApp

Create a generic messaging port under:

```text
communication/whatsapp/
```

Core:

```text
WhatsAppMessage
WhatsAppSender
```

Provider-specific implementation:

```text
communication/whatsapp/providers/meta/
```

Do not expose provider SDK objects outside the adapter.

---

## 11.16 Localization / Multilanguage

Create a small localization abstraction.

Concepts:

```text
Locale
TranslationKey
Translator
TranslationCatalog
```

Support locale fallback.

Do not build a giant custom i18n framework.

Keep backend translations suitable for:

- transactional email;
- notification text;
- generated documents;
- validation/business messages where appropriate.

The frontend may have its own translation package.

---

## 11.17 Styling

Styling is not a backend concern.

Do NOT attempt to implement a frontend component framework inside Python.

Instead provide only shared backend-safe design metadata if useful, e.g.:

```text
brand name
logo URL/reference
primary color token
document/email theme settings
```

Define a small typed `Branding` model if needed.

Clearly document that reusable React/Svelte styling/components belong in a separate frontend package.

---

## 11.18 Realtime updates

Create a transport-neutral realtime abstraction.

Concepts:

```text
RealtimeEvent
RealtimePublisher
Subscription
Topic
```

Adapters:

```text
realtime/memory/
realtime/sse/
realtime/websocket/
```

Optionally prepare a Redis adapter interface without forcing Redis as a mandatory dependency.

Domain modules publish events through a protocol.

They must not know whether the transport is:

- SSE;
- WebSocket;
- Redis Pub/Sub.

FastAPI provides the HTTP/WebSocket/SSE transport adapters.

---

# 12. Events

Build a small application event mechanism.

Do not build Kafka internally.

Define:

```python
class Event(Protocol):
    @property
    def event_name(self) -> str: ...
```

and:

```python
class EventPublisher(Protocol):
    async def publish(
        self,
        events: tuple[Event, ...],
    ) -> None: ...
```

Provide an in-process implementation.

Example events:

```text
UserCreated
UserDeactivated
MembershipAdded
PasswordResetRequested
SubscriptionChanged
NotificationCreated
```

Modules communicate through events where direct synchronous dependency would create unnecessary coupling.

Keep events immutable.

---

# 13. Database architecture

Use SQLAlchemy 2.x modern typed ORM.

Use:

```python
Mapped[T]
mapped_column(...)
```

Do not use legacy SQLAlchemy query syntax.

Use async SQLAlchemy.

Provide:

```text
AsyncEngine
async_sessionmaker
AsyncSession
```

Session ownership must be explicit.

Repositories must not create hidden global sessions.

Transactions should be controlled at an appropriate application boundary.

Avoid repository methods committing independently unless explicitly designed that way.

Prefer one transaction for one application operation.

Build a small Unit of Work only if it clearly improves transaction ownership.

Do not add one merely because Clean Architecture examples do.

---

# 14. Database models vs domain models

Do not make SQLAlchemy models automatically become the domain model for every feature.

Prefer separating persistent ORM records from domain values where this provides useful boundaries.

However, avoid pointless mapping layers for trivial CRUD-only records.

Make pragmatic decisions feature by feature.

Document each important decision.

---

# 15. Migrations

Use Alembic.

The foundation package owns migrations for tables it owns.

Design a mechanism allowing a consuming application to include foundation migrations together with application-specific migrations.

Do not rely on manually copying SQL files.

Document:

- initial setup;
- migration execution;
- version upgrades;
- what happens when a foundation release introduces a schema migration.

Migration scripts must be committed.

---

# 16. FastAPI integration

FastAPI is an adapter, not the center of the architecture.

Create reusable route factories/routers.

Example:

```python
def create_auth_router(
    service: AuthService,
) -> APIRouter: ...
```

Do not rely on hidden global singletons.

Create explicit dependency factories where useful.

Provide routers for:

- auth;
- users;
- organizations;
- teams;
- notifications;
- billing where appropriate.

Do not force every consuming application to expose every route.

The consuming application chooses which routers to include.

Example application:

```python
app.include_router(auth_router)
app.include_router(user_router)
```

---

# 17. Application composition

Create a clear composition root.

Example:

```text
example_app/
├── main.py
├── container.py
└── settings.py
```

`container.py` may explicitly wire dependencies, but it must NOT become a runtime service locator.

Example style:

```python
user_repository = SqlAlchemyUserRepository(session_factory)
user_service = UserService(user_repository)

password_hasher = Argon2PasswordHasher()
token_issuer = JwtTokenIssuer(settings.jwt)

auth_service = AuthService(
    users=user_service,
    password_hasher=password_hasher,
    token_issuer=token_issuer,
)
```

Dependencies must be obvious from constructors.

---

# 18. Configuration

Use `pydantic-settings`.

Configuration must be explicit and typed.

Examples:

```text
DatabaseSettings
JwtSettings
EmailSettings
GoogleOAuthSettings
StripeSettings
WhatsAppSettings
```

Secrets must not have meaningful development defaults.

Never commit real credentials.

Provide `.env.example`.

Do not make the domain depend on settings classes.

Only adapters/composition root should read configuration.

---

# 19. Optional dependencies / extras

The base package must remain reasonably small.

Provider SDKs should be optional dependencies.

Create extras where useful.

Target usage such as:

```bash
uv add "app-foundation[postgres,google,stripe,email]"
```

Potential extras:

```text
postgres
google
stripe
smtp
whatsapp
realtime
documents
all
```

Do not create an extra for every tiny feature.

Core business modules should remain available without importing optional provider libraries.

Use Python 3.15 lazy imports where they give a real benefit for optional/heavy adapters.

---

# 20. Public API

Every feature should deliberately expose its public API through `__init__.py`.

Example:

```python
from .models import User, UserId
from .protocols import UserRepository
from .service import UserService

__all__ = (
    "User",
    "UserId",
    "UserRepository",
    "UserService",
)
```

Keep internal implementation details internal.

Use leading `_` and/or internal subpackages appropriately.

Do not export SQLAlchemy implementation details from the feature's root API.

---

# 21. Package typing

Ship:

```text
py.typed
```

The built wheel must include it.

The library must be usable as a fully typed package by consuming projects.

Add a test that verifies package typing/import behavior after building the wheel.

---

# 22. Ruff

Configure Ruff aggressively but pragmatically.

Enable a broad useful rule set including categories such as:

- E
- F
- W
- I
- UP
- B
- SIM
- C4
- PERF
- RUF
- ARG
- ANN where useful
- ASYNC
- TRY
- RET
- PTH
- PIE
- T20
- S where appropriate

Do not blindly enable contradictory or unsuitable rules.

Document intentional ignores.

Use Ruff for both:

```bash
uv run ruff check .
uv run ruff format --check .
```

And fixing:

```bash
uv run ruff check --fix .
uv run ruff format .
```

Use a modern line length, preferably 100.

---

# 23. ty

Configure ty in `pyproject.toml`.

Make static typing strict.

The command:

```bash
uv run ty check
```

must pass.

Where Python 3.15 targeting must be specified explicitly, configure it.

Do not suppress errors globally to make the build green.

Any local suppression must include a short reason.

---

# 24. Testing

Use pytest.

Tests must be divided into:

```text
tests/unit/
tests/integration/
tests/architecture/
```

Unit tests:

- domain;
- services;
- authorization;
- events;
- value objects;
- error paths.

Integration tests:

- SQLAlchemy repositories;
- migrations;
- FastAPI routers;
- PostgreSQL behavior where database semantics matter.

Architecture tests should verify important dependency rules where feasible.

Examples:

- core `billing` must not import Stripe;
- core `auth` must not import Google SDK;
- domain modules must not import FastAPI;
- core modules must not import SQLAlchemy adapters;
- no forbidden `utils` or `helpers` dumping-ground package appears.

Use fakes/in-memory adapters for fast unit tests.

Do not mock every internal method.

Prefer testing through public behavior.

---

# 25. Security

Apply secure defaults.

Requirements:

- Argon2 password hashing;
- constant-time comparisons where relevant;
- JWT validation;
- access-token expiry;
- refresh token rotation;
- refresh token revocation;
- OAuth state validation;
- secure random token generation;
- webhook signature verification;
- no secrets in logs;
- no plaintext MFA recovery codes;
- no plaintext password-reset tokens at rest where avoidable;
- rate-limit interfaces/hooks for public auth operations;
- CSRF considerations where cookie-based auth is demonstrated;
- CORS configuration belongs to application composition;
- input validation at API boundaries;
- authorization checks separate from authentication.

Do not invent custom cryptography.

---

# 26. Observability

Use Python's standard `logging` architecture or a minimal structured logging setup.

Create contextual logging support without leaking secrets.

Support correlation/request IDs.

Provide interfaces/hooks for:

- metrics;
- tracing;
- audit events.

Do not force one commercial observability platform.

---

# 27. Audit

Provide a small audit abstraction.

Examples:

```text
user.created
user.updated
user.deactivated
membership.added
role.assigned
subscription.cancelled
```

Audit records should be immutable append-style records.

Do not mix audit logs with ordinary debug logs.

---

# 28. Timestamps and clocks

Do not scatter direct calls to `datetime.now()` throughout business logic.

Create a small clock protocol where deterministic time matters.

Use timezone-aware UTC datetimes internally.

Example:

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```

Provide:

```text
SystemClock
FixedClock
```

Use `FixedClock` in tests.

---

# 29. IDs

Use typed domain IDs instead of passing arbitrary strings everywhere.

Choose a simple consistent implementation.

Possible examples:

```python
type UserId = UUID
type TeamId = UUID
```

or small frozen value objects where stronger separation is valuable.

Do not introduce heavyweight abstractions around UUIDs without a concrete benefit.

Use UUIDv7 if it is well-supported by the targeted Python 3.15 standard library/environment and it benefits sortable identifiers; otherwise choose a clear documented UUID strategy.

---

# 30. Pagination

Create one simple reusable pagination model where needed.

Do not build an enormous generic query framework.

Prefer cursor pagination for large feeds where appropriate.

Offset pagination is acceptable for ordinary administration screens.

---

# 31. Result objects

Do not introduce a custom `Result[T, E]` type everywhere merely to imitate Rust.

Use normal Python return values and domain-specific exceptions unless a result type has a clear practical advantage.

---

# 32. Dependency direction

Enforce these rules:

```text
domain/application
    ↓
protocols
    ↓
adapters
```

Allowed conceptually:

```text
SQLAlchemy adapter -> identity protocol/domain
Stripe adapter     -> billing protocol/domain
Google adapter     -> auth oauth protocol/domain
SMTP adapter       -> email protocol/domain
FastAPI adapter    -> application services
```

Forbidden:

```text
identity -> SQLAlchemy
billing -> Stripe
auth core -> Google
notification -> SMTP
domain -> FastAPI
domain -> Pydantic Settings
```

Pydantic may be used at boundaries and for typed DTO/configuration where appropriate.

Avoid making Pydantic the universal domain-model base class.

---

# 33. Reusability between customer projects

The foundation package must not contain customer-specific domain concepts.

Forbidden examples:

```text
Building
Machine
InvoiceApprovalForCustomerX
SPSController
ConstructionProject
```

Those belong to consuming applications.

Foundation should only contain broadly reusable application capabilities.

---

# 34. Versioning

Use Semantic Versioning.

Examples:

```text
1.4.2 -> patch fix
1.5.0 -> backwards-compatible capability
2.0.0 -> breaking public API change
```

Keep:

```text
CHANGELOG.md
```

Document breaking changes and migration instructions.

The package version must have one authoritative source.

Prefer automated version derivation from release tags if this remains simple.

Do not duplicate versions manually in many files.

---

# 35. Distribution

The foundation must support distribution through:

- a private Python package registry;
- PyPI-compatible registries;
- optionally direct Git dependencies during development.

Target consuming-project usage:

```bash
uv add app-foundation
```

or:

```bash
uv add "app-foundation[postgres,google,stripe]"
```

Document private registry configuration without embedding credentials.

Build:

```bash
uv build
```

Publish:

```bash
uv publish
```

Provide instructions for publishing a new version.

---

# 36. Update workflow for consuming projects

Design and document the expected lifecycle:

```text
foundation change
        ↓
tests + lint + types
        ↓
release/tag
        ↓
build package
        ↓
publish package
        ↓
consumer receives dependency-update PR
        ↓
consumer test suite
        ↓
merge
```

Never force all customer applications to automatically run new untested foundation code.

A customer application pins/ranges the dependency through `uv.lock`.

Recommend an automated dependency updater such as Renovate or Dependabot where appropriate.

The update remains a normal reviewed PR.

---

# 37. CI

Create CI configuration appropriate for a Git repository.

Pipeline must run:

```bash
uv sync --all-extras --dev
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
uv build
```

Also test installation/import of the built wheel.

If Python 3.15 is prerelease in the current environment, make CI compatible with the prerelease until final is published.

Avoid unnecessary matrix explosion.

---

# 38. Development commands

Provide short commands/documentation for:

```bash
uv sync
uv run fastapi dev ...
uv run pytest
uv run ruff check .
uv run ruff format .
uv run ty check
uv build
uv publish
```

Optionally add a Makefile as a convenience wrapper, but uv commands remain the source of truth.

---

# 39. Package boundaries

Use one distributable package initially.

Do NOT begin with 17 separately published Python packages.

Use:

```text
app-foundation
```

with internal feature modules.

Only split a feature into a separately versioned distribution later if there is a demonstrated independent lifecycle.

The initial goal is a modular foundation monolith, not package fragmentation.

---

# 40. Example consumer project

Create:

```text
examples/example_app/
```

Demonstrate a minimal FastAPI project consuming the package.

The example should wire:

- PostgreSQL/SQLAlchemy;
- users;
- auth;
- RBAC;
- notifications;
- FastAPI routers.

It must show clearly that customer-specific modules live outside the foundation.

Do not let the example application become part of the published package.

---

# 41. Public package ergonomics

Aim for clean imports.

Good:

```python
from app_foundation.auth import AuthService
from app_foundation.identity import UserService
from app_foundation.access_control import Authorizer
```

Avoid:

```python
from app_foundation.auth.application.services.impl.default_auth_service import ...
```

Internals may be organized deeply, but the public API should remain concise.

---

# 42. Documentation

Create a useful `README.md`.

It must contain:

1. purpose;
2. architecture;
3. requirements;
4. installation;
5. quick start;
6. database setup;
7. migrations;
8. FastAPI setup;
9. enabling optional adapters;
10. testing;
11. typing;
12. linting;
13. building;
14. publishing;
15. versioning;
16. upgrading;
17. adding a new feature module;
18. adding a new provider/adapter;
19. dependency rules.

Also add concise architectural decision records under:

```text
docs/adr/
```

At minimum:

```text
0001-modular-foundation.md
0002-ports-and-adapters.md
0003-single-distribution.md
0004-sqlalchemy-boundary.md
0005-event-boundary.md
```

Keep ADRs concise.

---

# 43. Avoid overengineering

Do not introduce:

- CQRS unless clearly needed;
- event sourcing;
- Kafka;
- Celery;
- Redis;
- dependency injection frameworks;
- repository base classes;
- abstract factories everywhere;
- custom ORM;
- custom validation framework;
- custom cryptography;
- custom HTTP framework;
- custom type-checker configuration generators.

A small, explicit implementation is preferred.

Additional infrastructure should be replaceable through ports.

---

# 44. Code quality rules

Follow these rules consistently:

- small classes/functions;
- one responsibility per module;
- explicit constructor dependencies;
- no mutation of input parameters;
- minimal global state;
- immutable domain values where useful;
- descriptive names;
- no hidden I/O;
- no hidden DB commits;
- no circular imports;
- no star imports;
- no wildcard public APIs;
- no unnecessary decorators;
- no metaclass magic;
- no dynamic monkey patching;
- no runtime import tricks where normal Python works;
- no premature abstraction;
- no speculative generic framework.

Prefer simple readable Python.

---

# 45. `__init__.py`

Use explicit package exports.

Each feature should expose only its intended public API.

Example:

```python
from .models import User, UserId
from .protocols import UserRepository
from .service import UserService

__all__ = (
    "User",
    "UserId",
    "UserRepository",
    "UserService",
)
```

Do not use:

```python
from .models import *
```

---

# 46. FastAPI request/response schemas

Keep API schemas separate from domain entities when HTTP-specific representation differs.

Do not return SQLAlchemy models directly.

Use Pydantic response/request schemas.

Map explicitly.

Avoid pointless duplicate DTOs if shapes are truly identical and no boundary benefit exists.

---

# 47. Repository behavior

Repository interfaces should represent domain persistence needs, not database operations.

Good:

```python
class UserRepository(Protocol):
    async def get_by_email(self, email: EmailAddress) -> User | None: ...
    async def add(self, user: User) -> None: ...
```

Avoid generic database-shaped APIs such as:

```python
filter_by(...)
query(...)
execute_raw(...)
find_all_where(...)
```

unless an infrastructure-specific API explicitly requires it.

---

# 48. Provider/accessor/service terminology

Where useful, use these meanings consistently:

```text
Repository
    persistence abstraction for domain entities

Provider
    external capability implementation/abstraction,
    e.g. OAuthProvider, PaymentProvider

Accessor
    read-oriented access abstraction where that term adds clarity

Service
    application/domain orchestration

Handler
    entry-point adapter,
    e.g. HTTP handler/webhook handler/job handler
```

Do not create all four for every feature just to satisfy a pattern.

Only create a layer if it has a responsibility.

---

# 49. Exhaustiveness

Where there is a closed set of variants and missing handling would be dangerous, use Python's type system and `match` statements to make the handling as exhaustive as possible.

Use enums/literals/sealed-by-convention unions where suitable.

Make ty catch missing or incompatible handling where supported.

Do not create enum factories merely to mimic Java unless the Python model benefits from it.

---

# 50. Plugin/provider extension model

A new provider should be addable without modifying the business core.

Examples:

```text
PaymentProvider
├── StripePaymentProvider
└── FutureAdyenPaymentProvider

OAuthProvider
├── GoogleOAuthProvider
└── FutureMicrosoftOAuthProvider

EmailSender
├── SmtpEmailSender
└── FutureResendEmailSender
```

Do not build a dynamic plugin discovery framework initially.

Explicit dependency injection is enough.

---

# 51. Example required architecture

The final project should conceptually resemble:

```text
                     consuming application
                              │
                       composition root
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
        FastAPI             Jobs              Webhooks
          │                   │                   │
          └──────────── application services ─────┘
                              │
             ┌────────────────┼────────────────┐
             │                │                │
          identity          auth           billing
             │                │                │
          protocols        protocols        protocols
             │                │                │
      ┌──────┴──────┐   ┌─────┴─────┐    ┌─────┴─────┐
      │             │   │           │    │           │
 SQLAlchemy       memory Google   local  Stripe    fake
```

Dependencies point inward toward stable contracts.

---

# 52. What to implement first

Build incrementally in this order:

1. project/tooling skeleton;
2. config primitives;
3. events;
4. identity;
5. organization;
6. access control;
7. auth;
8. Google OAuth;
9. MFA;
10. communication/email;
11. notification;
12. system notifications;
13. jobs;
14. realtime;
15. billing/Stripe;
16. addresses;
17. scheduling/reminders;
18. documents;
19. WhatsApp;
20. localization;
21. observability/audit;
22. example app;
23. package build/publish configuration;
24. CI;
25. documentation.

At every stage keep:

```bash
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

green.

---

# 53. First implementation expectations

Do not create 500 empty placeholder files.

Implement a useful vertical slice before moving to the next module.

For example, identity should include:

- domain model;
- repository protocol;
- SQLAlchemy persistence;
- service;
- API schemas;
- router;
- migration;
- unit tests;
- integration tests.

Then proceed.

Provider-heavy modules can initially include one real provider plus an in-memory/fake implementation.

---

# 54. Deliverables

Create all of the following:

```text
pyproject.toml
uv.lock
.python-version
README.md
CHANGELOG.md
LICENSE
Makefile
.env.example
src/app_foundation/**
tests/**
migrations/**
docs/adr/**
examples/example_app/**
CI configuration
```

Also provide:

- complete folder tree;
- architecture explanation;
- setup commands;
- development commands;
- test commands;
- build commands;
- publish commands;
- example consumer integration;
- example release/update workflow.

---

# 55. Validation before finishing

Before considering the task complete:

1. install dependencies with uv;
2. format with Ruff;
3. lint with Ruff;
4. run ty;
5. run unit tests;
6. run integration tests possible in the environment;
7. build sdist;
8. build wheel;
9. install the built wheel into a clean temporary environment;
10. import the public package API;
11. confirm `py.typed` is included;
12. confirm optional dependencies do not break base-package imports;
13. confirm core modules do not import provider SDKs;
14. confirm there are no circular imports;
15. confirm the example FastAPI application starts.

Fix errors instead of documenting them as future work whenever reasonably possible.

---

# 56. Working style

Do not ask me to approve every file.

Make sensible architectural decisions and continue.

When there are multiple reasonable options:

1. choose the simplest production-quality option;
2. document the choice briefly;
3. implement it consistently.

Do not stop after generating an architecture diagram.

Do not give me pseudo-code in place of implementation.

Do not leave core functionality as TODOs.

Do not generate fake implementations pretending to be production integrations.

For external providers that cannot be exercised without credentials, implement the adapter correctly, test its mapping/validation with fakes or mocked external boundaries, and document how credentials are supplied.

---

# 57. Desired result

The final result should feel like a small professional internal platform package that can be reused across many applications.

A new application should be able to:

```bash
uv init customer-app
uv add "app-foundation[postgres,google,stripe]"
```

and then explicitly compose only the capabilities it needs.

The foundation should make common concerns reusable without becoming a framework that controls the whole application.

Prioritize:

```text
clarity
type safety
explicit dependencies
testability
replaceability
small public APIs
stable package boundaries
easy upgrades
```

over cleverness.

Build it now.
