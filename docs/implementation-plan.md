# Role-Aware Access Control: Implementation Plan

**Goal:** Admin, Manager and Member access levels, enforced by the backend and reflected by the frontend, on a populated production database.
**Decisions and rules:** `CLAUDE.md` (numbered decisions D1 to D12). **Spec:** `TASK.md`.
**Every step:** branch from `dev`, failing test first, implement, review subagent, fix findings, then merge when backend tests, Playwright and lint are green.

## Step 1: Role column and migration — `feat/rbac-role-migration`
Schema changes; the API contract does not. All existing tests must pass without edits, which is the proof that nobody's access changed.
- **Files:** `backend/app/models.py` (`Role` StrEnum; `User.role` with server default and CHECK built from the enum; `is_superuser` leaves the table), `backend/app/alembic/versions/<rev>_add_user_role_drop_is_superuser.py` (`down_revision = fe56fa70289e`, order and downgrade per D2, literal role strings because migrations are frozen snapshots), `backend/app/crud.py`, `backend/app/core/db.py`.
- **Temporary shim, fully removed in step 2:** API schemas keep `is_superuser`, so the OpenAPI schema and generated client are unchanged. Read: derived from `role`. Write: one trivial mapping in `crud.py` used by both create and update (`true` to `ADMIN`, `false` to `MEMBER`, unset on update leaves the role alone). No test is written for the shim itself.
- **Tests:** `backend/tests/migrations/test_role_migration.py`, four tests that run the Alembic CLI against a throwaway database (dropped in teardown even on failure): superusers map to `admin` and others to `member` with `is_active` unchanged; an insert without a role gets `member`; an unknown role is rejected; downgrade restores `is_superuser` only for admins.
- **Done:** migration test passes; 58 backend and 62 Playwright tests pass unchanged; `generate-client.sh` produces no diff; `alembic upgrade head` then `downgrade -1` then `upgrade head` works on the local populated database.

## Step 2: Backend authorization and API contract — `feat/rbac-backend-authz`
- **Files (backend):** `backend/app/core/permissions.py` (new: `Permission`, `ROLE_PERMISSIONS`, `permissions_for(role)`, `has_permission(user, permission)`, `can_access_item(user, item)`, `can_delete_own_account(user)`, `ensure_active_admin_remains(...)` raising `LastAdminError`), `backend/app/api/deps.py` (`require_permission`; 401 codes per D3; `get_current_active_superuser` removed), `backend/app/api/routes/users.py`, `items.py`, `login.py`, `utils.py`, `backend/app/api/routes/metrics.py` (new stub: user and item counts, behind `metrics:read`), `backend/app/api/main.py`, `backend/app/models.py` (`role` replaces `is_superuser` in API schemas, shim removed; `UserMePublic` with `permissions`), `backend/app/crud.py`.
- **Permission per endpoint:** list users and read another user: `users:read`. Create, update, delete user, test email, password-recovery HTML: `users:manage`. Metrics: `metrics:read`.
- **Files (contract adaptation only, so the frontend still builds):** regenerated `frontend/src/client/`, `frontend/src/lib/permissions.ts` (new: `hasPermission`), `AppSidebar.tsx`, `routes/_layout/admin.tsx`, `routes/_layout/settings.tsx`, `Admin/columns.tsx`, `Admin/AddUser.tsx` and `Admin/EditUser.tsx` (checkbox becomes a role select); `frontend/tests/admin.spec.ts` ("Create a superuser" only).
- **Tests:** `backend/tests/core/test_permissions.py` (every `Role` has an entry). `backend/tests/api/routes/test_access_control.py`: role by endpoint matrix including a manager reading and updating another user's item; a token issued before demotion gets 403 and before deactivation gets 401 with `WWW-Authenticate: Bearer`; signup, update-me and `/private/users/` cannot set `role` or `is_active` (assert database rows); manager and member `PATCH /users/{id}` with `role=admin`, on themselves and on others, get 403 with no change; the only admin cannot be demoted, deactivated or deleted (409), and with two admins one can demote the other; a `PATCH` of an admin that omits `role` leaves the role unchanged. Existing tests that use `is_superuser` switch to `role`; `backend/tests/utils/user.py` gains a create-user-with-role helper.
- **Done:** all backend tests green with coverage at 90% or more; no `is_superuser` left outside migrations; `User` inherits `UserBase` again and the temporary field declarations from step 1 are gone; Playwright green, including "Redirects to /login when token is wrong"; client committed in this branch.

## Step 3: Frontend access rules — `feat/rbac-frontend-access`
- **Files:** `frontend/src/lib/permissions.ts` (adds the `beforeLoad` guard), `frontend/src/hooks/useAuth.ts` (shared current-user query options), `frontend/src/main.tsx` (401 and 403 handling per D10), `frontend/src/components/Common/Forbidden.tsx` (new), `frontend/src/routes/_layout/admin.tsx` (guard on `users:read`; add control gated by `users:manage`), `frontend/src/routes/_layout/metrics.tsx` (new stub page, guard on `metrics:read`), `frontend/src/routeTree.gen.ts`, `AppSidebar.tsx` (links by permission), `Admin/UserActionsMenu.tsx` (edit and delete gated by `users:manage`).
- **Tests:** `frontend/tests/admin.spec.ts` ("Non-superuser cannot access admin page" now expects the Forbidden page). `frontend/tests/access-control.spec.ts` (new): a manager sees the users table without add, edit or delete controls and can open metrics; a member gets Forbidden on `/metrics`. `frontend/tests/utils/privateApi.ts` gains a helper that creates a user with a role through the authenticated admin API.
- **Done:** Playwright green; in Chrome, each role sees the right navigation, a direct visit to a forbidden URL shows Forbidden with no flash and no page data request, and demoting a logged-in manager takes effect on their next action without a reload or a redirect loop.

## Step 4: Demo users and instructions — `feat/rbac-demo-users`
- **Files:** `backend/app/seed_demo_users.py` (new, per D11), `development.md` (the seed command and the three logins).
- **Tests:** `backend/tests/scripts/test_seed_demo_users.py`, one test that pins the development-only guard.
- **Done:** from a fresh database, the documented commands give three working logins through both `uv run python app/seed_demo_users.py` and `docker compose exec backend python app/seed_demo_users.py`; a second run changes nothing; the script refuses to run without `FASTAPI_ENV=development`; final check of all three roles in Chrome.

## Then
One PR from `dev` to `master` with all CI checks green. `deploy.yml` will fail after that merge because the repository has no deploy secrets; that is expected.

## Review focus (not pinned by a test)
- Two admins demoting each other at the same moment: covered by the row lock, verified by reading the transaction code.
- A role lowered while a page is open: verified in Chrome in step 3.
- The seed script against a database where the demo emails already exist with other roles: verified by hand in step 4.
