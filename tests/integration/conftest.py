import pytest

from tests.fixtures import canned_event_page  # re-export for tests


@pytest.fixture
def event_page():
    return canned_event_page()
