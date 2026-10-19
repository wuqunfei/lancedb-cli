"""Tests for lsql.core.parsing."""

import pytest

from lsql.core.exceptions import CommandError
from lsql.core.parsing import parse_embedding_columns


def test_parse_embedding_columns_single_source_defaults_to_vector():
    source, target = parse_embedding_columns("name", None)
    assert source == ["name"]
    assert target == ["vector"]


def test_parse_embedding_columns_multi_source_defaults_to_suffixed_names():
    source, target = parse_embedding_columns("name,city", None)
    assert source == ["name", "city"]
    assert target == ["name_vector", "city_vector"]


def test_parse_embedding_columns_explicit_target_overrides_default():
    source, target = parse_embedding_columns("name,city", "vec1,vec2")
    assert source == ["name", "city"]
    assert target == ["vec1", "vec2"]


def test_parse_embedding_columns_strips_whitespace():
    source, target = parse_embedding_columns(" name , city ", " vec1 , vec2 ")
    assert source == ["name", "city"]
    assert target == ["vec1", "vec2"]


def test_parse_embedding_columns_mismatched_counts_raises():
    with pytest.raises(CommandError, match="must pair up one-to-one"):
        parse_embedding_columns("name,city", "vec1")


def test_parse_embedding_columns_empty_source_raises():
    with pytest.raises(CommandError, match="at least one column"):
        parse_embedding_columns("", None)
