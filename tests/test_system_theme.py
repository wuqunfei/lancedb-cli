from unittest.mock import patch

from lsql.core.system_theme import system_prefers_dark


def test_system_prefers_dark_returns_a_bool():
    assert isinstance(system_prefers_dark(), bool)


def test_system_prefers_dark_falls_back_to_true_on_any_failure():
    with patch("lsql.core.system_theme.sys") as mock_sys:
        mock_sys.platform = "some-exotic-os"
        with patch("lsql.core.system_theme._linux_prefers_dark", side_effect=RuntimeError("boom")):
            assert system_prefers_dark() is True
