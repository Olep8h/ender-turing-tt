# CLAUDE.md

Task: role-aware access control (Admin, Manager, Member) per `TASK.md`, on an app treated as already deployed with a populated database. Steps: `docs/implementation-plan.md`.

## Commands
- Services: `docker compose up -d db mailpit`. Migrate and seed admin, from `backend/`: `uv run bash scripts/prestart.sh`.
- Backend tests, from `backend/`: `uv run bash scripts/test.sh` (baseline 58 passed; CI fails under 90% coverage).
- Playwright, from `frontend/`: `bunx playwright test` (baseline 62 passed).
- Lint as CI does, from the root: `uv run prek run --from-ref origin/dev --to-ref HEAD`.
- Regenerate the API client, from the root: `bash scripts/generate-client.sh`.
- Known template quirks, out of scope: `--all-files` lint fails on DTZ011 in `scripts/`; `tests/` is not in the backend image.

## Decisions
1. **Role storage.** `Role` StrEnum (`ADMIN`, `MANAGER`, `MEMBER`), no raw role strings outside it. Column `user.role`: varchar, NOT NULL, server default `member`, CHECK constraint. `is_superuser` is dropped.
2. **Migration.** Upgrade order: add column with default, `UPDATE role='admin' WHERE is_superuser`, add CHECK, drop `is_superuser`. `is_active` untouched; nobody becomes manager. Downgrade: re-add `is_superuser` NOT NULL default false, true where admin, drop `role`. Managers become regular users (lossy, no privilege gain), stated in a comment.
3. **Sessions.** JWT carries only `sub`; role and `is_active` are read from the database on every request. `get_current_user` returns 401 with `WWW-Authenticate: Bearer` for a bad token, a deleted user or a deactivated user. 403 means authenticated but forbidden. Login with an inactive account stays 400.
4. **Policy module.** `backend/app/core/permissions.py`, no FastAPI imports: `Permission` StrEnum, `ROLE_PERMISSIONS`, and object-level rules that return bool or raise a domain exception. Default deny. Routes use `require_permission(...)` from `deps.py` and never name a role.
5. **Permissions.** `users:read`, `users:manage`, `metrics:read`, `items:manage_any`. Admin: all four. Manager: `users:read`, `metrics:read`. Member: none. No speculative permissions.
6. **Last admin.** At least one active admin must remain: applies to role change, deactivation and `DELETE /users/{id}`. Lock active-admin rows `FOR UPDATE ORDER BY id` in the same transaction as the update. Violation returns 409. An admin still cannot delete themselves (template rule kept).
7. **Items.** Unchanged behavior: without `items:manage_any` a user works only with their own items, filtered in SQL. Existing status codes, messages and item tests stay as they are.
8. **Escalation.** `role` and `is_active` are writable only through `POST /users/` and `PATCH /users/{id}`, both behind `users:manage`. Signup, update-me and `/private/users/` carry no privilege fields and always produce a member.
9. **Frontend access.** `GET /users/me` returns `role` and `permissions`. All checks go through `hasPermission` in one file; `role` is display-only. No copy of `ROLE_PERMISSIONS` in the frontend.
10. **Frontend errors.** 401 clears the token and goes to `/login`. 403 refetches `/users/me` once and never retries the forbidden request. Guards run in `beforeLoad` on the existing `/users/me` query (`queryClient.query`, 10-second `staleTime`) and render a minimal Forbidden page inside the layout, URL unchanged, before any page query fires.
11. **Demo users.** Opt-in `backend/app/seed_demo_users.py`: development only, uses `crud.create_user`, skips existing emails, never changes an existing role, prints the three logins.
12. **Tests.** Focused on security: migration (throwaway database, dropped in teardown), every role has a policy entry, role by endpoint matrix (including other users' items), existing sessions, escalation and null inputs (assert database state), last admin, the seed script's development-only guard, and Playwright for the three roles. Only two existing Playwright tests may change: "Non-superuser cannot access admin page" and "Create a superuser".

## Working rules
- **Scope.** Only what `TASK.md` requires. No unrelated refactoring, no new infrastructure, no visual polish, no extra docs.
- **Priorities for every change.** Correctness, security, maintainability, consistency with existing template patterns, migration safety, scope control.
- **Clean code.** Authorization logic in one place, separated from route handlers and UI components. Readable names. No duplication of rules between files.
- **Git flow.** One `feat/*` branch per plan step, branched from `dev`. Small conventional commits. Merge to `dev` only when tests and lint pass and review findings are resolved. `master` receives only one final PR from `dev`. Never commit directly to `dev` or `master`.
- **CI.** Reuse the existing GitHub Actions workflows. Only adjust triggers so tests and lint run on PRs to `dev` and `master` (they already do: `pull_request` has no branch filter). Do not add new pipelines.
- **Per step.** Write the failing test first for security-critical behavior, implement, then dispatch a separate code-review subagent that checks the diff against the six priorities above. Fix findings before merging.
- **Generated client.** Regenerate with `scripts/generate-client.sh` and commit it in the same branch as any backend schema change.
- **Tools.** modern-web-guidance for frontend work; the playwright skill and Chrome for verifying the three roles in the browser; Perplexity only for a specific question the repo and official docs cannot answer.
- **Ask me before any decision not covered here.**
