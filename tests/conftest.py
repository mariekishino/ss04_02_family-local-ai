import pytest

from family_ai import db
from family_ai.calendar_tools import build_registry
from family_ai.context import RequestContext


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def ctx():
    return RequestContext(actor_user_id="test_user", household_id="hh_test")


@pytest.fixture
def other_ctx():
    """別世帯の context。分離テスト用。"""
    return RequestContext(actor_user_id="stranger", household_id="hh_other")


@pytest.fixture
def registry():
    return build_registry()
