import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Set the database URL before importing application modules; SQLAlchemy engines
# are created at module import time.
_test_db = Path(tempfile.gettempdir()) / "tri9t_ct200_pytest.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"

@pytest.fixture
def client():
    from app.main import app
    from app.db import Base, engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c
    Base.metadata.drop_all(bind=engine)
