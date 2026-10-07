# Changelog

## 0.1.0 — 2026-10-06

Initial foundation distribution: identity, organizations, scoped RBAC, password/JWT/OAuth/MFA authentication, notifications and communication, jobs, realtime, billing, documents, addresses, reminders, localization, and observability.

Includes typed ports, memory and SQLAlchemy adapters, packaged Alembic revisions, Stripe/Google/Meta/SMTP integrations, an example consumer, PostgreSQL integration tests, architecture checks, and clean-wheel verification.

Initial schema: `af0001`; `af0002` adds tenant-consistent team membership and notification visibility. Apply `alembic upgrade heads` before starting an application. No previous released API exists to migrate.
