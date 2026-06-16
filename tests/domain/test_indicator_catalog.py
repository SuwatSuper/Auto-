# Layer 1 — Domain (tests/domain/test_indicator_catalog)
"""Tests for the indicator knowledge catalogue (the agent's declarative vocabulary)."""
from __future__ import annotations

import pytest

from domain.analytics import indicator_catalog as cat
from domain.analytics import indicator_lines as il

# Expected line count per family (groups 1..9).
_GROUP_SIZES = {1: 7, 2: 3, 3: 3, 4: 8, 5: 5, 6: 4, 7: 7, 8: 5, 9: 3}


def test_catalogue_has_all_45_lines() -> None:
    assert len(cat.all_lines()) == 45
    assert sum(_GROUP_SIZES.values()) == 45


def test_numbers_are_1_to_45_unique() -> None:
    numbers = sorted(line.number for line in cat.all_lines())
    assert numbers == list(range(1, 46))


def test_keys_are_unique() -> None:
    keys = cat.keys()
    assert len(keys) == 45
    assert len(set(keys)) == 45


def test_every_group_is_named_and_sized() -> None:
    for group, size in _GROUP_SIZES.items():
        lines = cat.by_group(group)
        assert len(lines) == size, f"group {group} should hold {size} lines"
        assert group in cat.GROUP_NAMES_TH
        assert lines[0].group_name_th == cat.GROUP_NAMES_TH[group]


def test_by_key_roundtrips_and_raises_on_unknown() -> None:
    for line in cat.all_lines():
        assert cat.by_key(line.key) is line
    with pytest.raises(KeyError):
        cat.by_key("does_not_exist")


def test_by_category_partitions_every_line() -> None:
    categories = {line.category for line in cat.all_lines()}
    covered = sum(len(cat.by_category(c)) for c in categories)
    assert covered == 45
    assert cat.by_category("momentum")  # non-empty


def test_each_line_has_thai_text_and_a_resolvable_compute_ref() -> None:
    for line in cat.all_lines():
        assert line.name_en and line.name_th and line.description_th
        # Every catalogued line names a real callable/constant in indicator_lines.
        assert hasattr(il, line.compute), f"{line.key}: missing impl '{line.compute}'"


def test_inputs_use_known_series_names() -> None:
    allowed = {"open", "high", "low", "close", "volume", "level"}
    for line in cat.all_lines():
        assert set(line.inputs) <= allowed, f"{line.key}: bad inputs {line.inputs}"
