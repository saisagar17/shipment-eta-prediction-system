import pytest

from data_generation.config import Config
from data_generation.pipeline import generate


@pytest.fixture(scope="session")
def tables():
    return generate(Config())
