# Welcome to the Pekno Community! 🎉

Pekno is the core AI-Native Knowledge OS of **Project Cardinal**.
We are currently in **Phase 0: Genesis Iteration**, which means the system is moving fast, ideas are still being tested, and thoughtful contributors can shape the foundation.

Whether you fix a typo, improve a paragraph, report a confusing setup step, build a plugin, or refactor a core subsystem, your contribution matters. Pekno is a playground for **Homelab builders**, **AI hackers**, and people who believe personal knowledge infrastructure should be open, hackable, and self-hosted.

## How to Contribute

- **Report Bugs 🐛**
  - Open a GitHub Issue.
  - Include your OS, Docker version, deployment mode, logs, screenshots, and reproduction steps.
  - If the issue touches ML or media processing, include whether you are using `cpu`, `cuda`, or another runtime.

- **Propose Ideas**
  - Use GitHub Discussions or Issues to share ideas, rough designs, plugin concepts, and workflow improvements.
  - Early-stage ideas are welcome. Phase 0 is where strange ideas become architecture.

- **Contribute Code 🚀**
  - Fork the repository.
  - Create a focused branch.
  - Keep changes small enough to review.
  - Follow the local setup and development rules below.

## Local Setup

### Prerequisites

Install these tools first:

- `Git`
- `Docker` and Docker Compose
- `Python 3.13`
- `Node.js`
- `uv` for Python dependency management

Recommended environment:

- `Linux` or `WSL` is best.
- Native Windows can work, but Docker runs inside WSL and editing Windows-mounted files from WSL can cause permission, path, newline, or file watcher issues.
- If you use Windows, prefer keeping the repository inside the WSL filesystem.

### Backend Setup

Clone and enter the repository:

```bash
git clone https://github.com/Sat1n/Pekno.git
cd Pekno
```

Install Python dependencies with `uv`:

```bash
uv sync --frozen
```

Create a local environment file:

```bash
cp .env.example .env.local
cp .env.local .env
```

Start infrastructure services with Docker if needed:

```bash
docker compose up -d postgres redis
```

Start the Hub with automatic Alembic migration handling:

```bash
./scripts/start-hub-with-migrate.sh
```

Start a worker in another terminal:

```bash
./scripts/start-worker.sh
```

Start the scheduler in another terminal:

```bash
./scripts/start-scheduler.sh
```

You can also use the combined helper:

```bash
./scripts/start-all.sh
```

### Frontend Setup

Install frontend dependencies:

```bash
cd web
npm install
```

Run the Vite development server:

```bash
npm run dev
```

The production Docker entrypoint uses `docker-entrypoint.sh` and `scripts/smart_migrate.py` to perform safe migration `stamp` or `upgrade` behavior at startup.

## Development Philosophy

- **Toolchain**
  - Python backend dependency management is `uv` only.
  - Do not use `pip`, `pip freeze`, or `poetry` to mutate project dependencies.
  - Dependency changes must update both `pyproject.toml` and `uv.lock`.

- **Database**
  - Do not manually edit database tables.
  - Do not use `Base.metadata.create_all()`.
  - All schema changes must be represented by Alembic migrations.
  - Before opening a PR with schema changes, run:

```bash
uv run alembic revision --autogenerate -m "describe your schema change"
```

- **Architecture Boundaries**
  - Hub is the FastAPI control plane: API routing, authorization, database state changes, and queue dispatch.
  - Worker owns heavy processing: plugin execution, `extract_text_for_ai()`, OCR/transcription, summaries, tags, embeddings, and media/document AI work.
  - Scheduler should stay lightweight. It triggers auto-sync, heartbeat/cleanup, and AI sweep/fan-out jobs, but it should not fetch remote content or run model workloads.
  - Redis/Taskiq is the async boundary. Long-running work should be decomposed into worker tasks when practical instead of blocking a single scheduler trigger.

- **Plugin and AI Processing**
  - Plugin authors should implement source-aware `extract_text_for_ai()`; Pekno uses that hook for normal sync, single-item parsing, long summaries, and incremental AI processing.
  - `enable_incremental_ai_sync` is a system-scoped framework setting. Plugin code should not branch on it directly.
  - Items use `ai_processing_status` values `pending_ai`, `processing`, and `completed`. Schema changes around this state must include Alembic migrations.
  - Keep user-uploaded document/media processing separate from plugin sync unless a shared worker helper explicitly supports both paths.

- **Code Style**
  - Keep code readable, typed where practical, and boring in the best way.
  - Use Black/Ruff-compatible formatting for Python code.
  - If pre-commit hooks are available in your local setup, install and run them before pushing:

```bash
pre-commit install
pre-commit run --all-files
```

- **Frontend Text**
  - Do not hardcode user-facing UI strings directly in Vue components.
  - Use i18n keys and update both `web/src/i18n/en.json` and `web/src/i18n/zh-CN.json`.

## Testing Notes

For focused backend changes, prefer running the smallest meaningful pytest set first, then expand if the change crosses subsystem boundaries:

```bash
uv run pytest tests/test_plugin_summary_pipeline.py tests/test_search_relevance.py
```

For schema, plugin, worker, or scheduler changes, include migration checks and at least one worker-facing test or compile check:

```bash
uv run python -m compileall shared hub worker
git diff --check
```

## GitHub Flow

Use small, focused branches:

- `feature/plugin-marketplace`
- `fix/docker-migration`
- `docs/quick-start`

Use Conventional Commit-style prefixes:

```text
feat: add plugin sync controls
fix: handle empty credential vault entries
docs: clarify production compose setup
chore: update release metadata
```

Typical PR flow:

```bash
git fork
git checkout -b feature/my-change
git add .
git commit -m "feat: describe my change"
git push origin feature/my-change
```

Then open a Pull Request on GitHub.

Before a PR is merged, GitHub Actions will run CI checks. Keep the PR description clear:

- What changed?
- Why does it matter?
- How was it tested?
- Are there migration, deployment, or plugin compatibility notes?

## License & CLA

By submitting code, documentation, tests, or other contributions, you agree that your contribution is provided under the same **MIT License** terms as Pekno.

Do not submit code that you cannot legally license under `MIT`, and do not introduce dependencies or copied code that conflict with MIT License distribution.
