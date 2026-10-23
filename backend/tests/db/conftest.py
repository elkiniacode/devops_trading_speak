import pytest

from app import db


@pytest.fixture(autouse=True)
def db_file(tmp_path):
    """Every db test gets a fresh, seeded database, closed afterwards."""
    path = tmp_path / "data" / "finally.db"
    db.init_db(path)
    yield path
    db.close_db()
