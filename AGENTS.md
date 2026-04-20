# AGENTS.md

## System Role & Context

- **Project Name:** `Pekno`, the core AI-Native Knowledge OS of `Project Cardinal`.
- **Current Phase:** `Phase 0` / `Genesis Iteration`; expect rapid iteration and unstable internal contracts.
- **License:** `MIT`; do not generate code that introduces incompatible license restrictions or copied code that cannot be distributed under the MIT License.
- **Agent Objective:** Read this document before modifying code to understand architectural boundaries, development constraints, and red lines.

## Architecture Topology

- **Hub:** `FastAPI` service for API routing, database state changes, and authorization checks.
  - Do not run heavy ML workloads here.
  - Do not perform blocking I/O in request handlers.
- **Worker:** `Taskiq` workflow node for async processing.
  - Owns multimodal model execution such as `Whisper` / `ctranslate2`.
  - Owns plugin execution and plugin sandbox boundaries.
  - CPU and CUDA execution modes are selected and adapted here.
- **Scheduler:** `Taskiq Beat` node.
  - Only triggers scheduled polling jobs such as plugin `Auto-sync`.
  - Do not put processing, network-heavy ingestion, or ML work here.
- **Nginx:** unified traffic gateway.
  - Serves frontend static files.
  - Reverse proxies `/api`.
  - Handles MCP long-lived protocol connections.
- **Frontend:** `Vue 3` + `Vite`.
  - Fully separated from backend runtime concerns.
  - Communicates with Hub through HTTP APIs and MCP-facing endpoints.

## Core Development Conventions

- **Development Environment**
  - Prefer `Linux` or `WSL`.
  - Native Windows development is riskier because Docker runs inside WSL, and editing Windows-mounted files from WSL can cause permission, path, newline, or file watcher issues.
  - Check the local development environment before changing build, Docker, filesystem, or watcher behavior.
- **Dependency Management**
  - Use `uv` strictly.
  - Do not use `pip` or `poetry`.
  - Dependency changes must be reflected in `pyproject.toml` and `uv.lock`.
- **Database Migrations**
  - Never use `Base.metadata.create_all()`.
  - All schema changes must go through `alembic revision --autogenerate`.
  - Runtime startup uses the smart migrator from `docker-entrypoint.sh` to perform `stamp` or `upgrade`.
- **Credential Management**
  - Never hardcode secrets in plugins.
  - Use the global credential vault backed by `UserCredentialORM`.
  - Plugins should only declare credential requirements through `required_credentials` in their manifest.
- **Internationalization**
  - Do not hardcode Chinese UI text in frontend code.
  - All frontend UI text must use `$t()` and be extracted into `web/src/i18n/zh-CN.json` and `web/src/i18n/en.json`.
  - Backend exceptions must use standardized error codes.

## File Tree Mapping

- `hub/api/routers/` -> RESTful endpoints.
- `worker/plugins/` -> plugin implementations and manifests.
- `shared/database.py` and `shared/models.py` -> SQLAlchemy database wiring and ORM definitions.
- `web/src/views/` and `web/src/components/` -> frontend UI.
- `docker/` -> Nginx configs and deployment-related Docker assets.
- `docker-compose.yaml` -> local build-oriented orchestration.
- `docker-compose.prod.yml` -> prebuilt-image production orchestration.
- `.github/workflows/` -> GitHub Actions automation.
