# Capability and validation map

All foundation modules are implemented under `src/app_foundation`. This map distinguishes runnable behavior from deliberately replaceable interfaces. External provider tests use mocked network boundaries; live provider accounts are not exercised.

| Capability | Implemented behavior | Evidence |
| --- | --- | --- |
| Identity | Unique normalized email, profile updates, active state, timestamps, typed IDs; memory and SQLAlchemy persistence | `test_identity_auth.py`, PostgreSQL uniqueness/rollback tests, user HTTP tests |
| Organizations and teams | Creation, scoped membership roles/state, invitations and acceptance; tenant-consistent team foreign key | Organization/RBAC unit tests and API/PostgreSQL tests |
| Access control | Consumer-defined roles/permissions, scoped assignments, membership-gated authorization, owner policy | Cross-tenant denial and HTTP ownership tests |
| Auth | Argon2, validated JWTs, sessions, refresh rotation/reuse revocation, verification/reset, persistent throttling | Unit and concurrent PostgreSQL auth tests |
| OAuth | Google code exchange, PKCE/state/nonce, verified identity, explicit linking, MFA challenge | Provider mapping and OAuth state tests |
| MFA | Encrypted TOTP enrollment, confirmation, replay counters, hashed recovery codes, reauthenticated disable | MFA lifecycle and concurrent recovery consumption tests |
| Email | Plain/HTML messages, attachments, CC/BCC/reply-to, SMTP and memory senders | MIME/privacy tests; verification queue used in PostgreSQL tests |
| Notifications | Per-channel preferences, persistent in-app feed/read state, transactional outbound work, retries | Delivery/ownership tests; queue rollback/visibility integration test |
| Jobs | Registry, interval/cron scheduling, coalesced ticks, graceful shutdown, memory/PostgreSQL locks | Job exclusion and PostgreSQL advisory-lock tests |
| Realtime | Neutral events, bounded memory subscriptions, SSE/WebSocket authorization and cleanup | Broker tests; example mounts both transports |
| Billing | Customers, product/price values, checkout, subscriptions, cancellation, signed/idempotent webhooks | Stripe HTTP/signature tests and concurrent webhook integration tests |
| Addresses | Immutable postal/location values and normalization/validation ports | Address validation tests |
| Scheduling | Persistent calendar events and reminders; one-off/daily/weekly triggers and cancellation | Recurrence/DST unit test; migration coverage |
| Documents | HTML templates/context, escaping, storage separation, private filesystem and memory adapters | Rendering and path-traversal tests |
| WhatsApp | Typed text/template messages, Meta Graph API and memory adapters | HTTP mapping and provider-failure tests |
| Localization | Catalog lookup, regional/language/default fallback, parameter substitution | Translation tests |
| Branding | Typed backend branding metadata | Public model/type checks |
| Events/audit | Immutable application events, transaction-delayed in-process publication, transactional append audit sink | Rollback integration tests and explicit example composition |
| Observability | Correlation IDs, redacting logging filter, vendor-neutral metrics/tracing interfaces | Example HTTP startup/request-ID test and type checks |
| Distribution | Typed wheel/sdist, packaged migrations, base-only imports, extras, external consumer typing | `scripts/check_distribution.py` |

## Master prompt sections

| Sections | Implementation and verification |
| --- | --- |
| 1–3: baseline, Python, package goal | `pyproject.toml`, `.python-version`, `uv.lock`, `src/` package |
| 4–7: architecture, layout, naming | Feature modules, explicit protocols/adapters, five ADRs, architecture tests |
| 8–10: typing, immutability, errors | All ty rules set to error, annotated public interfaces, frozen values, adapter exception translation |
| 11: required features | Capability table above; no frontend component framework |
| 12: events | `events`, caller-owned transactional event publication |
| 13–15: database/model separation/migrations | Async repositories, `Transaction`, packaged `af0001`/`af0002`, migration round-trip/drift tests |
| 16–18: HTTP/composition/settings | Feature router factories, explicit example scopes, typed environment settings |
| 19–21: extras/public API/typing package | Optional extras, explicit exports, `py.typed`, clean-wheel verification |
| 22–24: Ruff/ty/tests | Broad lint rules, strict typing, unit/integration/architecture suites |
| 25: security | Auth/OAuth/MFA, signed webhooks, safe credential storage, rate-limiter protocols and PostgreSQL implementation |
| 26–28: observability/audit/clocks | Context logging, append audit records, metrics/tracing hooks, injected clocks |
| 29–31: IDs/pagination/results | UUIDv7/NewType IDs, small page values, normal exceptions; refresh rejection is an explicit commit-sensitive result |
| 32–33: dependency direction/customer isolation | Architecture tests and example-owned application policy |
| 34–36: version/distribution/updates | Single metadata version, changelog, registry/release/consumer update instructions |
| 37–38: CI/development commands | GitHub Actions with PostgreSQL, Makefile, README commands |
| 39–41: package boundaries/example/ergonomics | One distribution, standalone consumer example, concise feature exports |
| 42: documentation | README, this map, tree, glossary, five ADRs |
| 43–49: simplicity/quality/exports/schemas/repositories/terminology/exhaustiveness | Protocol composition, mapped HTTP schemas, domain-shaped repository methods, enum state handling |
| 50–51: extension model/architecture | Explicit provider injection; domain code never imports its provider adapter |
| 52–53: incremental vertical slices | Implemented modules have working behavior; production adapters are distinct from named test fakes |
| 54–55: artifacts and verification | Root deliverables, CI, distribution checker and executable tests |
| 56–57: working result | Installable reusable foundation and explicit consumer composition |

## Deliberate limits

PDF/DOCX rendering, external calendars/geocoders, alternative OAuth/payment providers, distributed realtime brokers, and frontend components are extension points as specified in the prompt. Additional organizational groups are not needed alongside organizations and teams in this release. Base schema installation creates all foundation tables, regardless of which routers a consumer exposes.

Delivery is at least once, realtime is process-local, and in-process events have no replay log. Memory repositories are single-process test adapters; PostgreSQL tests establish concurrency semantics. These limits are documented contracts rather than production adapters silently using fakes.

## Provider references

- [Google OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect): provider claims, nonce, and state.
- [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests): provider request keys.
- [Alembic branches](https://alembic.sqlalchemy.org/en/latest/branches.html): independently owned version locations.
- [SQLAlchemy 2.1 changes](https://docs.sqlalchemy.org/en/21/changelog/changelog_21.html): Python 3.15 support.
- [ty configuration](https://docs.astral.sh/ty/reference/configuration/): explicit Python targeting and diagnostics.
