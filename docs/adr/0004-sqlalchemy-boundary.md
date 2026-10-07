# SQLAlchemy owns persistence details

Keep mapped records inside adapters and domain values independent of SQLAlchemy. Repositories flush within caller-owned transactions; packaged Alembic branches evolve foundation tables alongside consumer migrations without copying SQL. Shared tenant tables require explicit organization predicates and database constraints.
