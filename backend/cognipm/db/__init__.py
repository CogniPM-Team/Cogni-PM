"""Database access (PostgreSQL).

  migrations/    numbered .sql files, applied once each by migrate.apply_migrations().
  connection.py  connect() / get_connection() (the latter also applies pending migrations).
  audit.py       log_audit(): appends to audit_log, which a trigger makes append-only.

Schema changes go in a NEW numbered migration file; never edit one that has been merged.
"""
