from app.services.pattern import parse_pattern


def test_multiline_with_blank_lines_and_whitespace():
    result = parse_pattern("Row 1\n\nRow 2\n  Row 3  ")
    assert result == [(1, "Row 1"), (2, "Row 2"), (3, "Row 3")]


def test_empty_string_returns_empty():
    assert parse_pattern("") == []


def test_whitespace_only_returns_empty():
    assert parse_pattern("   \n\n  ") == []


def test_single_line():
    assert parse_pattern("Row 1") == [(1, "Row 1")]


def test_windows_line_endings():
    result = parse_pattern("Row 1\r\nRow 2\r\nRow 3")
    assert result == [(1, "Row 1"), (2, "Row 2"), (3, "Row 3")]


def test_trailing_whitespace_stripped():
    result = parse_pattern("  Row 1  \n  Row 2  ")
    assert result == [(1, "Row 1"), (2, "Row 2")]
