import * as cp from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as vscode from 'vscode';
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
  TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

const EXTENSION_ID = 'nimpsch.gh-formatter-vscode';
const DEFAULT_FORMATTER_PROMPTED_KEY = 'gh-formatter.defaultFormatterPrompted';

// No `language` filter here on purpose: GitHub's own "GitHub Actions"
// extension (github.vscode-github-actions) reassigns workflow files to a
// separate language id, `github-actions-workflow`, instead of `yaml` --
// see https://github.com/redhat-developer/vscode-yaml/issues/1086 for the
// same problem hitting another YAML tool. Matching on the file path alone
// works regardless of which language id ends up assigned.
const DOCUMENT_SELECTOR = [
  { scheme: 'file', pattern: '**/.github/workflows/**/*.{yml,yaml}' },
  { scheme: 'file', pattern: '**/action.{yml,yaml}' },
];

// Same default-strategy split as Microsoft's Python tool extensions
// (black-formatter, pylint, ...): 'useBundled' runs the copy of
// gh-formatter shipped inside this extension (bundled/libs/, populated by
// scripts/vendor_libs.sh at package time) so nothing needs pip-installing;
// 'fromEnvironment' instead uses whatever gh-formatter-lsp is already
// installed in the project, so it matches a pinned pre-commit/CI version.
const PYTHON_CANDIDATES = process.platform === 'win32' ? ['py', 'python'] : ['python3', 'python'];

function findPythonInterpreter(): string | undefined {
  for (const candidate of PYTHON_CANDIDATES) {
    try {
      cp.execFileSync(candidate, ['--version'], { stdio: 'ignore' });
      return candidate;
    } catch {
      // Not on PATH (or not runnable) -- try the next candidate.
    }
  }
  return undefined;
}

/** Whether `command` resolves to an executable file on PATH, without
 * running it (gh-formatter-lsp has no quick sanity-check flag -- it just
 * starts an LSP session over stdio, so invoking it to "check" would hang). */
function commandExistsOnPath(command: string): string | undefined {
  const dirs = (process.env.PATH ?? '').split(path.delimiter);
  const names =
    process.platform === 'win32' ? [`${command}.exe`, `${command}.cmd`, `${command}.bat`] : [command];
  for (const dir of dirs) {
    for (const name of names) {
      const candidate = path.join(dir, name);
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        return candidate;
      } catch {
        // Not here -- keep looking.
      }
    }
  }
  return undefined;
}

/** `.venv/bin/gh-formatter-lsp` in the first workspace folder, else
 * whatever's resolvable on PATH; undefined if neither exists. */
function findEnvironmentServer(): string | undefined {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (folder) {
    const venvBin =
      process.platform === 'win32'
        ? path.join(folder.uri.fsPath, '.venv', 'Scripts', 'gh-formatter-lsp.exe')
        : path.join(folder.uri.fsPath, '.venv', 'bin', 'gh-formatter-lsp');
    if (fs.existsSync(venvBin)) {
      return venvBin;
    }
  }
  return commandExistsOnPath('gh-formatter-lsp');
}

function toServerOptions(command: string, args: string[] = []): ServerOptions {
  return {
    run: { command, args, transport: TransportKind.stdio },
    debug: { command, args, transport: TransportKind.stdio },
  };
}

/** The bundled copy: any Python 3 interpreter on PATH running
 * bundled/tool/lsp_server.py, which puts bundled/libs/ on sys.path. */
function resolveBundledServerOptions(
  context: vscode.ExtensionContext
): ServerOptions | undefined {
  const python = findPythonInterpreter();
  if (!python) {
    vscode.window.showErrorMessage(
      "gh-formatter: no Python interpreter found (tried 'python3'/'python' on PATH). " +
        'Install Python 3, or set gh-formatter.serverPath to an installed gh-formatter-lsp.'
    );
    return undefined;
  }
  const script = context.asAbsolutePath(path.join('bundled', 'tool', 'lsp_server.py'));
  return toServerOptions(python, [script]);
}

function resolveServerOptions(
  context: vscode.ExtensionContext
): ServerOptions | undefined {
  const cfg = vscode.workspace.getConfiguration('gh-formatter');

  const serverPath = cfg.get<string>('serverPath');
  if (serverPath) {
    return toServerOptions(serverPath);
  }

  const strategy = cfg.get<string>('importStrategy', 'useBundled');
  if (strategy === 'fromEnvironment') {
    const envServer = findEnvironmentServer();
    if (envServer) {
      return toServerOptions(envServer);
    }
    // Same fallback behavior as Black's/Ruff's VSCode extensions: don't
    // just fail when the environment copy is missing, use the bundled one.
    vscode.window.showWarningMessage(
      "gh-formatter: importStrategy is 'fromEnvironment' but no gh-formatter-lsp " +
        'was found in .venv or on PATH -- falling back to the bundled copy.'
    );
  }

  return resolveBundledServerOptions(context);
}

// Language ids whose editor.defaultFormatter we offer to set. Plain YAML
// covers everyone; github-actions-workflow additionally covers anyone with
// GitHub's own "GitHub Actions" extension installed, which reassigns
// workflow files to that language id instead of yaml (see the
// DOCUMENT_SELECTOR comment). Without that extension installed, workflow
// files stay plain yaml -- covering only github-actions-workflow would be
// a silent no-op for most users, so both are set.
const FORMATTER_LANGUAGE_IDS = ['yaml', 'github-actions-workflow'];

/**
 * Offers, once ever, to make this extension the default formatter for YAML
 * (with format-on-save) -- only after the server has actually started, and
 * only with explicit consent, since editor.defaultFormatter is scoped to
 * whole languages, not just the workflow/action files this extension
 * covers (see the README's "Known Limitations").
 *
 * `force` bypasses the "already asked" check, for the manual
 * "gh-formatter: Set as Default Formatter" command -- an escape hatch,
 * since dismissing the dialog (Escape / click-away, `choice` undefined)
 * without an explicit Yes/No otherwise permanently skips this on every
 * future activation.
 */
async function promptDefaultFormatter(
  context: vscode.ExtensionContext,
  force = false
): Promise<void> {
  if (!force && context.globalState.get<boolean>(DEFAULT_FORMATTER_PROMPTED_KEY)) {
    return;
  }

  const choice = await vscode.window.showInformationMessage(
    'Make gh-formatter the default formatter for YAML/GitHub Actions files and enable format on save?',
    'Yes',
    'No'
  );
  if (choice === undefined) {
    return; // Dismissed without an answer -- ask again next activation.
  }
  await context.globalState.update(DEFAULT_FORMATTER_PROMPTED_KEY, true);
  if (choice !== 'Yes') {
    return;
  }

  const settingsSnippet = FORMATTER_LANGUAGE_IDS.map(
    (id) => `"[${id}]": { "editor.defaultFormatter": "${EXTENSION_ID}", "editor.formatOnSave": true }`
  ).join('\n');
  try {
    for (const languageId of FORMATTER_LANGUAGE_IDS) {
      const editorConfig = vscode.workspace.getConfiguration('editor', { languageId });
      await editorConfig.update('defaultFormatter', EXTENSION_ID, vscode.ConfigurationTarget.Global, true);
      await editorConfig.update('formatOnSave', true, vscode.ConfigurationTarget.Global, true);
    }
  } catch (err) {
    vscode.window.showErrorMessage(
      `gh-formatter: could not update settings automatically (${err}). ` +
        `Add this to your settings.json instead:\n${settingsSnippet}`
    );
  }
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('gh-formatter.setDefaultFormatter', () =>
      promptDefaultFormatter(context, true)
    )
  );

  if (!vscode.workspace.getConfiguration('gh-formatter').get<boolean>('enable', true)) {
    return;
  }

  const serverOptions = resolveServerOptions(context);
  if (!serverOptions) {
    return; // resolveServerOptions already reported why
  }

  const clientOptions: LanguageClientOptions = {
    documentSelector: DOCUMENT_SELECTOR,
  };

  client = new LanguageClient(
    'gh-formatter',
    'gh-formatter Language Server',
    serverOptions,
    clientOptions
  );

  client.start().then(
    () => {
      void promptDefaultFormatter(context);
    },
    (err: unknown) => {
      vscode.window.showErrorMessage(
        `gh-formatter: failed to start the language server. ${err}`
      );
    }
  );

  context.subscriptions.push({ dispose: () => void client?.stop() });
}

export function deactivate(): Thenable<void> | undefined {
  return client?.stop();
}
