# tests/test_allocation.py
"""Contract stubs for the allocation engine (analyzers.allocation).

Documents the intended weighting API; assertions to be completed when the
engines are implemented — see INVESTMENT_PLAN.md §6.3 / §11.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analyzers import AllocationEngine
from src import config


def test_engine_defaults_match_config():
    eng = AllocationEngine()
    assert eng.single_name_cap == pytest.approx(0.08)
    assert eng.ai_semi_cap == pytest.approx(0.40)
    # config exposes the same guardrails the plan defines
    assert config.SINGLE_NAME_CAP == pytest.approx(0.08)
    assert config.AI_SEMI_CAP == pytest.approx(0.40)


def test_equal_weight_not_yet_implemented():
    eng = AllocationEngine()
    with pytest.raises(NotImplementedError):
        eng.equal_weight(['AAA', 'BBB'])
