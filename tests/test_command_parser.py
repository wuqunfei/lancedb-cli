import pytest

from lancedbx.commands.parser import (
    ArgParseExit,
    build_delete_parser,
    build_load_parser,
    build_query_parser,
    split_first_token,
    tokenize_rest,
)


def test_split_first_token_basic():
    assert split_first_token("/schema") == ("schema", "")


def test_split_first_token_strips_slash_and_lowercases():
    assert split_first_token("/QUERY --limit 5") == ("query", "--limit 5")


def test_split_first_token_blank_line():
    assert split_first_token("   ") == (None, "")


def test_split_first_token_preserves_unbalanced_quotes_in_rest():
    # shlex.split would choke on this; split_first_token must not touch `rest`.
    name, rest = split_first_token("/sql SELECT * FROM t WHERE name = 'O'Brien'")
    assert name == "sql"
    assert rest == "SELECT * FROM t WHERE name = 'O'Brien'"


def test_tokenize_rest_respects_quoting():
    assert tokenize_rest('--where "x > 5" --limit 3') == ["--where", "x > 5", "--limit", "3"]


def test_tokenize_rest_raises_valueerror_on_unbalanced_quotes():
    with pytest.raises(ValueError):
        tokenize_rest("--where 'unterminated")


def test_query_parser_defaults():
    args = build_query_parser().parse_args([])
    assert args.where is None
    assert args.limit == 10
    assert args.select is None
    assert args.output == "table"


def test_query_parser_parses_flags():
    args = build_query_parser().parse_args(["--where", "x > 5", "--limit", "3", "--output", "json"])
    assert args.where == "x > 5"
    assert args.limit == 3
    assert args.output == "json"


def test_query_parser_rejects_bad_output_choice():
    with pytest.raises(ArgParseExit):
        build_query_parser().parse_args(["--output", "xml"])


def test_delete_parser_requires_where():
    with pytest.raises(ArgParseExit):
        build_delete_parser().parse_args([])
    args = build_delete_parser().parse_args(["--where", "id = 1"])
    assert args.where == "id = 1"


def test_load_parser_requires_path_and_table():
    with pytest.raises(ArgParseExit):
        build_load_parser().parse_args(["--path", "x.csv"])
    args = build_load_parser().parse_args(["--path", "x.csv", "--table", "t", "--overwrite"])
    assert args.path == "x.csv"
    assert args.table == "t"
    assert args.overwrite is True


def test_parser_does_not_sys_exit_on_unknown_flag():
    # The real regression this guards against: argparse's default error() calls
    # sys.exit(), which would kill the whole Textual app.
    with pytest.raises(ArgParseExit):
        build_query_parser().parse_args(["--nope"])
