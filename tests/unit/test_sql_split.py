from __future__ import annotations

from pathlib import Path

from artek_buddy.db.sql_split import split_sql_statements

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "semicolon_in_function.sql"


def test_splits_on_real_statement_boundaries() -> None:
    sql = "CREATE TABLE a (id TEXT);\nCREATE TABLE b (id TEXT);"
    assert split_sql_statements(sql) == [
        "CREATE TABLE a (id TEXT)",
        "CREATE TABLE b (id TEXT)",
    ]


def test_keeps_semicolon_inside_single_quoted_string() -> None:
    sql = "INSERT INTO t (s) VALUES ('a;b'); SELECT 1;"
    parts = split_sql_statements(sql)
    assert parts == ["INSERT INTO t (s) VALUES ('a;b')", "SELECT 1"]


def test_keeps_semicolon_inside_line_and_block_comments() -> None:
    sql = """
    SELECT 1; -- ignore;
    /* also ; here */
    SELECT 2;
    """
    parts = split_sql_statements(sql)
    assert len(parts) == 2
    assert parts[0] == "SELECT 1"
    assert parts[1].rstrip().endswith("SELECT 2")
    assert "ignore;" in parts[1]
    assert "also ; here" in parts[1]
    assert len([p for p in sql.split(";") if p.strip()]) > 2


def test_nested_block_comment_does_not_split() -> None:
    sql = "SELECT 1 /* outer ; /* inner ; */ still ; comment */ ; SELECT 2;"
    assert split_sql_statements(sql) == [
        "SELECT 1 /* outer ; /* inner ; */ still ; comment */",
        "SELECT 2",
    ]


def test_dollar_parameter_is_not_a_quote() -> None:
    sql = "SELECT $1; SELECT $2;"
    assert split_sql_statements(sql) == ["SELECT $1", "SELECT $2"]


def test_fixture_function_is_one_statement_unlike_naive_split() -> None:
    sql = FIXTURE.read_text(encoding="utf-8")
    parts = split_sql_statements(sql)
    naive = [part.strip() for part in sql.split(";") if part.strip()]
    assert len(parts) == 1
    assert "RETURN 1;" in parts[0]
    assert "$artek$" in parts[0]
    assert "probe; value" in parts[0]
    assert len(naive) > 1
