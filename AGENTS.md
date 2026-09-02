# Repository Guidelines

## Project Structure & Module Organization

FLORIS is a Python package for wind farm wake modeling. Core package code lives in `floris/`, with physics and solver internals under `floris/core/`, optimization tools under `floris/optimization/`, turbine data under `floris/turbine_library/`, and default YAML inputs in `floris/default_inputs.yaml`. Tests are in `tests/`, including unit, integration, and regression suites. Usage examples and sample input files are in `examples/`. Documentation sources are in `docs/` and are built with Jupyter Book.

## Build, Test, and Development Commands

Set up a development environment from the repository root:

```bash
pip install -e ".[develop, docs]"
pre-commit install
```

Run the full test suite with:

```bash
pytest
```

Run targeted tests while developing:

```bash
pytest tests/*_unit_test.py
pytest tests/reg_tests/*_regression_test.py
```

Build local documentation with:

```bash
jupyter-book build docs/
```

The generated docs entry point is `docs/_build/html/index.html`.

## Coding Style & Naming Conventions

Use Python 3.10+ and keep code compatible with the versions declared in `pyproject.toml`. Follow the repository's existing Python style: 4-space indentation, descriptive snake_case for functions and variables, PascalCase for classes, and module names in lowercase with underscores when needed. Line length is 100 characters. Ruff and isort are configured in `pyproject.toml`; run them before committing:

```bash
ruff . --fix
isort floris tests
```

## Testing Guidelines

Tests use pytest. Name new tests consistently with the existing patterns, such as `*_unit_test.py`, `*_integration_test.py`, and `*_regression_test.py`. Add focused unit tests for low-level behavior and broader integration or regression tests when changing solver behavior, model outputs, or public workflows. Keep test data in `tests/data/` when shared across tests.

## Commit & Pull Request Guidelines

Recent history uses short imperative summaries and release/version commits, for example `Clean up grid classes (#1183)` and `Increment patch number`. Keep commit subjects concise and specific. Follow the documented Git Flow workflow: branch from the active development branch, keep changes focused, and sync before opening a pull request. Pull requests should describe the motivation, summarize behavior changes, link relevant issues or discussions, and report tests run. Include documentation updates for user-facing API, examples, configuration, or model behavior changes.

## Security & Configuration Tips

Do not commit local virtual environments, build outputs, caches, or private datasets. Treat YAML files in `examples/`, `tests/data/`, and `floris/turbine_library/` as versioned fixtures; update them deliberately and explain output-affecting changes in the pull request.
