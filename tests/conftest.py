import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_wall_data():
    """Load simple_wall.json fixture as a dict."""
    return json.loads((FIXTURES_DIR / "simple_wall.json").read_text())


@pytest.fixture
def house_model_data():
    """Load house_model.json fixture as a dict."""
    return json.loads((FIXTURES_DIR / "house_model.json").read_text())
