# Contributing to AURA

Thank you for your interest in contributing. This document covers how to set up the development environment, branch conventions, code style, and the pull request process.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Development Environment](#development-environment)
- [Branch and Commit Conventions](#branch-and-commit-conventions)
- [Backend Guidelines](#backend-guidelines)
- [Frontend Guidelines](#frontend-guidelines)
- [Training Pipeline Guidelines](#training-pipeline-guidelines)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

---

## Code of Conduct

Be respectful and constructive. This is an academic project; the goal is learning and collaboration.

---

## Development Environment

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 20+ |
| Docker | 24+ |
| Docker Compose | v2+ |
| Git | 2.40+ |

### First-time setup

```bash
git clone https://github.com/EponymousBearer/antibiotic-ai-cdss.git
cd antibiotic-ai-cdss
cp .env.example .env
```

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Frontend:

```bash
cd frontend
npm install
```

---

## Branch and Commit Conventions

### Branches

```
main           → stable, deployable
feature/<name> → new features
fix/<name>     → bug fixes
docs/<name>    → documentation only
chore/<name>   → tooling, deps, config
```

### Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

feat(api): add POST /recommend streaming support
fix(predictor): handle empty organism list on cold start
docs(readme): update quick-start docker command
chore(deps): bump catboost to 1.2.5
test(routes): add coverage for 400 validation errors
refactor(rules): simplify renal adjustment lookup
```

Types: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`, `perf`, `ci`

Scopes (optional): `api`, `frontend`, `predictor`, `rules`, `training`, `docker`, `ci`

---

## Backend Guidelines

### Style

- Follow [PEP 8](https://peps.python.org/pep-0008/). Use `black` for formatting.
- Type-annotate all function signatures.
- Keep route handlers thin — business logic belongs in `services/`.
- Pydantic models live in `schemas/`; never validate manually in routes.

### Adding a new endpoint

1. Define request/response schemas in `backend/app/schemas/request.py`.
2. Add business logic to an appropriate service in `backend/app/services/`.
3. Register the route in `backend/app/api/routes.py`.
4. Add at least one happy-path and one error-path test in `backend/tests/`.

### Adding a new antibiotic to the dosing engine

Edit `_init_dosing_database()` in `backend/app/services/rules.py`. Each entry must include:
- `adult_dose`, `pediatric_dose`
- `frequency`, `duration`
- `route_iv` (bool), `route_po` (bool)
- `renal_adjustment` (bool)
- `notes`

If `renal_adjustment` is `True`, add entries for `normal`, `mild`, `low`, and `severe` kidney function in the `renal_adjustments` dict inside `_adjust_for_renal()`.

---

## Frontend Guidelines

### Style

- TypeScript strict mode is enabled — no `any` escapes.
- Tailwind for styling; avoid inline styles.
- Components in `frontend/components/`, pages in `frontend/app/`.
- API calls only through `frontend/services/api.ts`.

### Adding a new page

1. Create `frontend/app/<route>/page.tsx`.
2. Keep data fetching inside the page component; pass props to presentational components.
3. Add a link to the new page from the relevant navigation location.

### Adding a new component

1. Create `frontend/components/MyComponent.tsx`.
2. Export it from `frontend/components/index.ts`.
3. Define props with an explicit TypeScript interface in the same file.

---

## Training Pipeline Guidelines

- All preprocessing changes go in `preprocess.py`. Never mutate the raw Dryad CSVs.
- Model quality threshold (AUC ≥ 0.65) is enforced in `train.py`. Do not lower it without discussion.
- After retraining, copy artifacts:
  ```bash
  cp training/output/antibiotic_model.pkl backend/model/
  cp training/output/model_metadata.json  backend/model/
  ```
- Commit the updated `model_metadata.json` but do **not** commit the `.pkl` file — it is large and binary. Use Git LFS or keep it out of version control.

---

## Testing

### Backend

```bash
cd backend
pytest tests/ -v --tb=short
```

Coverage report:

```bash
pytest tests/ --cov=app --cov-report=term-missing
```

All new backend code must include tests. Minimum requirements:
- Happy-path test for each new endpoint.
- At least one validation/error-path test.

### Frontend

```bash
cd frontend
npm run lint     # ESLint
npm run build    # Type check + production build
```

---

## Pull Request Process

1. Fork the repo and create a branch from `main`.
2. Make your changes, following the guidelines above.
3. Run tests and linting locally — do not open a PR with failing checks.
4. Open a PR against `main` with:
   - A clear title using Conventional Commits format.
   - A description explaining *what* changed and *why*.
   - Screenshots for any UI changes.
5. Request a review. Address all review comments before merging.
6. Squash-merge into `main`.

---

## Reporting Issues

Open a GitHub issue with:
- A clear title.
- Steps to reproduce.
- Expected vs. actual behaviour.
- Environment (OS, Python version, Node version, browser if applicable).
- Relevant logs or screenshots.

For security vulnerabilities, see [`SECURITY.md`](SECURITY.md).
