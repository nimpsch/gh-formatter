"""Lightweight smoke tests for the pygls glue in lsp/server.py.

Calls the plain handler functions directly against fake workspace/document
objects -- no real stdio JSON-RPC transport, per the project's testability
guideline of keeping protocol-level plumbing thin and covered by unit
tests on gh_formatter.lsp.core instead.
"""

from lsprotocol import types

from gh_formatter.lsp import server


class _FakeDocument:
    def __init__(self, path, source):
        self.path = path
        self.source = source
        self.lines = tuple(source.splitlines(True))


class _FakeWorkspace:
    def __init__(self, documents):
        self._documents = documents

    def get_text_document(self, uri):
        return self._documents[uri]


class _FakeLanguageServer:
    def __init__(self, documents):
        self.workspace = _FakeWorkspace(documents)
        self.published = []
        self.messages = []

    def text_document_publish_diagnostics(self, params):
        self.published.append(params)

    def window_show_message(self, params):
        self.messages.append(params)


def test_formatting_returns_whole_document_edit(tmp_path):
    path = tmp_path / "action.yml"
    messy = """
inputs:
  my-input:
    description: x
runs:
  using: composite
  steps:
    - shell: bash
      run: echo hi
name: My Action
"""
    uri = f"file://{path}"
    ls = _FakeLanguageServer({uri: _FakeDocument(str(path), messy)})

    edits = server.formatting(
        ls,
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            options=types.FormattingOptions(tab_size=2, insert_spaces=True),
        ),
    )

    assert edits is not None
    assert len(edits) == 1
    assert edits[0].new_text.index("name:") < edits[0].new_text.index("inputs:")


def test_formatting_returns_none_for_invalid_yaml(tmp_path):
    path = tmp_path / "ci.yml"
    invalid = "on:\n  push:\n    branches: [main\n"
    uri = f"file://{path}"
    ls = _FakeLanguageServer({uri: _FakeDocument(str(path), invalid)})

    edits = server.formatting(
        ls,
        types.DocumentFormattingParams(
            text_document=types.TextDocumentIdentifier(uri=uri),
            options=types.FormattingOptions(tab_size=2, insert_spaces=True),
        ),
    )

    assert edits is None


def test_did_save_publishes_parse_error_diagnostic(tmp_path):
    path = tmp_path / "ci.yml"
    invalid = "name: ci\non:\n  push:\n    branches: [main\njobs:\n  build:\n    runs-on: ubuntu-latest\n"
    uri = f"file://{path}"
    ls = _FakeLanguageServer({uri: _FakeDocument(str(path), invalid)})

    server.did_save(
        ls,
        types.DidSaveTextDocumentParams(
            text_document=types.TextDocumentIdentifier(uri=uri)
        ),
    )

    assert len(ls.published) == 1
    diagnostics = ls.published[0].diagnostics
    assert len(diagnostics) == 1
    assert diagnostics[0].severity is types.DiagnosticSeverity.Error
    assert diagnostics[0].range.start.line == 4  # 0-based; line 5 in the file


def test_did_close_clears_diagnostics(tmp_path):
    path = tmp_path / "ci.yml"
    uri = f"file://{path}"
    ls = _FakeLanguageServer({uri: _FakeDocument(str(path), "name: ci\n")})

    server.did_close(
        ls,
        types.DidCloseTextDocumentParams(
            text_document=types.TextDocumentIdentifier(uri=uri)
        ),
    )

    assert len(ls.published) == 1
    assert ls.published[0].diagnostics == []
