from gh-formatter.casing import format_casing


def test_camel_case():
    assert format_casing("myInput", "dash-case") == "my-input"
    assert format_casing("myInput", "snake_case") == "my_input"


def test_pascal_case():
    assert format_casing("MyInput", "dash-case") == "my-input"


def test_acronyms_kept_together():
    assert format_casing("myURLInput", "dash-case") == "my-url-input"
    assert format_casing("MyHTMLParser", "snake_case") == "my_html_parser"
    assert format_casing("apiURL", "dash-case") == "api-url"


def test_separators_normalized():
    assert format_casing("my input", "dash-case") == "my-input"
    assert format_casing("my__input", "dash-case") == "my-input"
    assert format_casing("my--input", "dash-case") == "my-input"


def test_leading_separators_stripped():
    assert format_casing("_private", "dash-case") == "private"
    assert format_casing("_private", "snake_case") == "private"


def test_already_formatted_unchanged():
    assert format_casing("already-fine", "dash-case") == "already-fine"
    assert format_casing("already_fine", "snake_case") == "already_fine"


def test_only_separators_left_untouched():
    assert format_casing("___", "dash-case") == "___"
