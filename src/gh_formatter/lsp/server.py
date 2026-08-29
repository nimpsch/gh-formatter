"""pygls-based Language Server exposing gh-formatter to editors.

Provides `textDocument/formatting` (against the live, possibly-unsaved
buffer) and diagnostics published on `textDocument/didOpen` and
`textDocument/didSave` -- deliberately not `didChange`, so YAML mid-edit is
never linted. `pygls` is a core dependency, so this is available whenever
gh-formatter itself is installed.
"""

from __future__ import annotations

import os

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from gh_formatter.config import Config, ConfigError
from gh_formatter.core.diagnostics import Diagnostic, Severity
from gh_formatter.core.pipeline import Engine
from gh_formatter.lsp.core import (
    ParseErrorLocation,
    diagnostic_to_lsp_range,
    run_pipeline,
)

SERVER_NAME = "gh-formatter-lsp"

server = LanguageServer(SERVER_NAME, "v0.1")
_engine = Engine()


def _config_for(ls: LanguageServer) -> Config:
    """Loads Config for the workspace; falls back to defaults on a bad file."""
    try:
        return Config.load()
    except ConfigError as e:
        ls.window_show_message(
            types.ShowMessageParams(
                type=types.MessageType.Warning, message=f"gh-formatter: {e}"
            )
        )
        return Config()


@server.feature(types.INITIALIZED)
def on_initialized(ls: LanguageServer, params: types.InitializedParams) -> None:
    """Moves into the workspace root for Config.load()'s cwd-based discovery.

    Multi-root workspaces are not supported in v1 -- only the (single)
    root reported by the client is honored.
    """
    root = ls.workspace.root_path
    if root:
        os.chdir(root)


@server.feature(types.TEXT_DOCUMENT_FORMATTING)
def formatting(
    ls: LanguageServer, params: types.DocumentFormattingParams
) -> list[types.TextEdit] | None:
    doc = ls.workspace.get_text_document(params.text_document.uri)
    outcome = run_pipeline(_engine, doc.source, doc.path, _config_for(ls))
    if outcome.formatted_text is None or outcome.formatted_text == doc.source:
        return None  # invalid YAML mid-edit, or already formatted: no-op

    whole_document = types.Range(
        types.Position(0, 0), types.Position(len(doc.lines), 0)
    )
    return [
        types.TextEdit(range=whole_document, new_text=outcome.formatted_text)
    ]


def _parse_error_diagnostic(
    error: ParseErrorLocation, source_lines: list[str]
) -> types.Diagnostic:
    start, end = diagnostic_to_lsp_range(error.line, error.column, source_lines)
    return types.Diagnostic(
        range=types.Range(types.Position(*start), types.Position(*end)),
        message=f"Invalid YAML: {error.message}",
        severity=types.DiagnosticSeverity.Error,
        source=SERVER_NAME,
    )


def _diagnostic_to_lsp(
    diag: Diagnostic, source_lines: list[str]
) -> types.Diagnostic:
    start, end = diagnostic_to_lsp_range(diag.line, diag.column, source_lines)
    severity = (
        types.DiagnosticSeverity.Error
        if diag.severity is Severity.ERROR
        else types.DiagnosticSeverity.Warning
    )
    return types.Diagnostic(
        range=types.Range(types.Position(*start), types.Position(*end)),
        message=diag.message,
        severity=severity,
        source=SERVER_NAME,
    )


def _publish(ls: LanguageServer, uri: str) -> None:
    doc = ls.workspace.get_text_document(uri)
    outcome = run_pipeline(_engine, doc.source, doc.path, _config_for(ls))

    source_lines = list(doc.lines)
    diagnostics: list[types.Diagnostic] = []
    if outcome.parse_error is not None:
        diagnostics.append(
            _parse_error_diagnostic(outcome.parse_error, source_lines)
        )
    diagnostics.extend(
        _diagnostic_to_lsp(d, source_lines) for d in outcome.diagnostics
    )

    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
    )


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(
    ls: LanguageServer, params: types.DidOpenTextDocumentParams
) -> None:
    _publish(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(
    ls: LanguageServer, params: types.DidSaveTextDocumentParams
) -> None:
    _publish(ls, params.text_document.uri)


@server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
def did_close(
    ls: LanguageServer, params: types.DidCloseTextDocumentParams
) -> None:
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(
            uri=params.text_document.uri, diagnostics=[]
        )
    )


def main() -> None:
    server.start_io()


if __name__ == "__main__":
    main()
