import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_SERVICE_URL", "http://llm.test")
os.environ.setdefault("IMAGE_SERVICE_URL", "http://image.test")
os.environ.setdefault("COST_SERVICE_URL", "http://cost.test")

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client():
    from app.database import Base, engine
    from app.main import app

    Base.metadata.create_all(bind=engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
