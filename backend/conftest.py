import pytest

import market_data


@pytest.fixture(autouse=True)
def _fresh_market_data_cache():
    market_data.clear_cache()
    yield
    market_data.clear_cache()
