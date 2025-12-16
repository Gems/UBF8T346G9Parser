# Repository Guidelines

## Project Structure & Module Organization
- Entry point: `parser_app.py` orchestrates reading Outlook backups and slicing message bodies.
- Modules: `backupreader/reader.py` pulls mail metadata from `Outlook.sqlite`; `olk15parser/parser.py` extracts HTML bodies; `helpers/helpers.py` collects user input and path validation. `htmlformater/` is reserved for output formatting extensions.
- Sample output: `MailArchive/` shows the expected HTML structure for archived mail; use it as a reference, not a source of fixtures.
- Legacy copies in `src/` mirror the main modules; update the top-level packages first and keep `src` in sync only if you rely on it.

## Build, Test, and Development Commands
- Run parser with interactive prompts for backup location/profile: `python3 parser_app.py`.
- Validate modules ad hoc: `python3 -m backupreader.reader` or `python3 -m olk15parser.parser` with temporary harness code if you need quick experiments.
- Lint/format (recommended even though not enforced): `python3 -m pip install ruff black` then `ruff check .` and `black .`.

## Coding Style & Naming Conventions
- Python 3 with 4-space indentation, type hints where practical, and small, single-purpose classes/functions.
- Keep names descriptive and lower_snake_case for functions, methods, and variables; classes are PascalCase.
- Prefer standard library modules (logging, pathlib, sqlite3) over new dependencies; avoid networked packages for privacy.

## Testing Guidelines
- No automated tests exist yet; add `pytest`-style tests that read from lightweight fixtures rather than real Outlook data.
- Name tests `test_<behavior>.py`; mock filesystem/database access or point to stripped-down `.olk15message` samples checked into a `tests/fixtures/` folder.
- Before merging, run any new tests with `pytest` and ensure the main script still runs against a small sample backup.

## Commit & Pull Request Guidelines
- Commit history favors short, descriptive imperatives (e.g., “Removed dataclass”, “Mail META data better formated”); follow that pattern.
- Keep PRs focused: describe user-facing changes, note data or schema expectations, and attach screenshots of generated HTML when UI changes occur.
- Reference related issues where available and call out any migration steps (new fixtures, sample data, or config knobs).

## Data Handling & Security
- Backups may contain sensitive mail; keep paths local, avoid uploading artifacts, and redact personal data in examples or logs.
- When sharing HTML output, strip message bodies or replace with sanitized samples to prevent accidental disclosure.
