# Project tree

Repository-local `.agents/` skills and generated caches/artifacts are omitted. The wheel contains only `app_foundation`; the example remains consumer code.

```text
corebox/
├── .github/
│   └── workflows/
│       └── ci.yml
├── docs/
│   ├── adr/
│   │   ├── 0001-modular-foundation.md
│   │   ├── 0002-ports-and-adapters.md
│   │   ├── 0003-single-distribution.md
│   │   ├── 0004-sqlalchemy-boundary.md
│   │   └── 0005-event-boundary.md
│   ├── capabilities.md
│   └── tree.md
├── examples/
│   └── example_app/
│       ├── __init__.py
│       ├── container.py
│       ├── dev.py
│       ├── main.py
│       ├── providers.py
│       ├── pyproject.toml
│       └── settings.py
├── migrations/
│   ├── env.py
│   └── script.py.mako
├── scripts/
│   └── check_distribution.py
├── src/
│   └── app_foundation/
│       ├── access_control/
│       │   ├── __init__.py
│       │   ├── memory.py
│       │   └── sqlalchemy.py
│       ├── addresses/
│       │   └── __init__.py
│       ├── api/
│       │   └── __init__.py
│       ├── auth/
│       │   ├── oauth/
│       │   │   ├── google/
│       │   │   │   └── __init__.py
│       │   │   ├── __init__.py
│       │   │   ├── api.py
│       │   │   └── state.py
│       │   ├── __init__.py
│       │   ├── adapters.py
│       │   ├── api.py
│       │   ├── email.py
│       │   ├── jobs.py
│       │   ├── memory.py
│       │   ├── mfa.py
│       │   ├── models.py
│       │   ├── protocols.py
│       │   ├── rate_limit.py
│       │   ├── service.py
│       │   └── sqlalchemy.py
│       ├── billing/
│       │   ├── providers/
│       │   │   ├── stripe/
│       │   │   │   └── __init__.py
│       │   │   └── __init__.py
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── jobs.py
│       │   ├── memory.py
│       │   └── sqlalchemy.py
│       ├── communication/
│       │   ├── email/
│       │   │   ├── __init__.py
│       │   │   └── smtp.py
│       │   ├── whatsapp/
│       │   │   ├── providers/
│       │   │   │   ├── meta/
│       │   │   │   │   └── __init__.py
│       │   │   │   └── __init__.py
│       │   │   └── __init__.py
│       │   └── __init__.py
│       ├── config/
│       │   └── __init__.py
│       ├── documents/
│       │   ├── __init__.py
│       │   └── adapters.py
│       ├── events/
│       │   └── __init__.py
│       ├── identity/
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── memory.py
│       │   ├── models.py
│       │   ├── protocols.py
│       │   ├── service.py
│       │   └── sqlalchemy.py
│       ├── jobs/
│       │   ├── __init__.py
│       │   └── postgres.py
│       ├── localization/
│       │   └── __init__.py
│       ├── notification/
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── jobs.py
│       │   ├── memory.py
│       │   ├── sqlalchemy.py
│       │   └── transports.py
│       ├── observability/
│       │   ├── __init__.py
│       │   └── sqlalchemy.py
│       ├── organization/
│       │   ├── __init__.py
│       │   ├── api.py
│       │   ├── memory.py
│       │   └── sqlalchemy.py
│       ├── persistence/
│       │   ├── migrations/
│       │   │   ├── versions/
│       │   │   │   ├── __init__.py
│       │   │   │   ├── af0001_initial_foundation_schema.py
│       │   │   │   └── af0002_tenant_constraints_and_notification_.py
│       │   │   └── __init__.py
│       │   ├── __init__.py
│       │   └── models.py
│       ├── realtime/
│       │   ├── __init__.py
│       │   ├── memory.py
│       │   ├── sse.py
│       │   └── websocket.py
│       ├── scheduling/
│       │   ├── __init__.py
│       │   ├── jobs.py
│       │   ├── memory.py
│       │   └── sqlalchemy.py
│       ├── __init__.py
│       ├── primitives.py
│       └── py.typed
├── tests/
│   ├── architecture/
│   │   └── test_dependencies.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_api.py
│   │   ├── test_postgres.py
│   │   └── test_realtime.py
│   ├── unit/
│   │   ├── test_failures.py
│   │   ├── test_identity_auth.py
│   │   ├── test_mfa_oauth.py
│   │   ├── test_modules.py
│   │   └── test_providers.py
│   ├── __init__.py
│   └── conftest.py
├── .env.example
├── .gitignore
├── .python-version
├── CHANGELOG.md
├── CONTEXT.md
├── LICENSE
├── Makefile
├── README.md
├── alembic.ini
├── compose.yaml
├── pyproject.toml
├── python_app_foundation_master_prompt.md
└── uv.lock
```
