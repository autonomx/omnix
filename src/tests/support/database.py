"""Test database URLs.

``OMNIX_TEST_DATABASE_URL`` is the role the application uses. CI also runs
the PostgreSQL tests as a restricted runtime role (DML only, subject to
row-level security); test setup that needs DDL or must bypass row-level
security uses ``OMNIX_TEST_ADMIN_DATABASE_URL`` (the DDL owner), which falls
back to the application URL when the two roles are the same.
"""
from __future__ import annotations

import os


def test_database_url() -> str:
    return os.environ["OMNIX_TEST_DATABASE_URL"]


def admin_database_url() -> str:
    return os.environ.get("OMNIX_TEST_ADMIN_DATABASE_URL") or test_database_url()
