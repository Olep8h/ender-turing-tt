import { type QueryClient, queryOptions } from "@tanstack/react-query"

import { type Permission, type UserMePublic, UsersService } from "@/client"

/**
 * Everything the frontend knows about access lives in this file.
 *
 * The permissions arrive from the backend with the current user, so the rules
 * for which role may do what exist only in the backend policy.
 */

// The current user, with their role and permissions. Components and route
// guards read the same cached query, so there is one answer to "who am I".
export const currentUserQueryOptions = queryOptions({
  queryKey: ["currentUser"],
  queryFn: async () => (await UsersService.readUserMe()).data,
})

export const hasPermission = (
  user: UserMePublic | null | undefined,
  permission: Permission,
): boolean => user?.permissions.includes(permission) ?? false

// The permission each guarded page needs. The sidebar and the route guards
// both read this map, so a page's rule is written once. A page that is not
// listed is open to every logged-in user.
export const routePermissions = {
  "/admin": "users:read",
  "/metrics": "metrics:read",
} as const satisfies Record<string, Permission>

type GuardedRoute = keyof typeof routePermissions

export const canOpenRoute = (
  user: UserMePublic | null | undefined,
  path: string,
): boolean =>
  !(path in routePermissions) ||
  hasPermission(user, routePermissions[path as GuardedRoute])

/** Thrown by a route guard. Guarded routes render it as the Forbidden page. */
export class ForbiddenError extends Error {}

// A guard may reuse an answer this recent. Older than that, or once a 403 has
// invalidated it, the guard asks the backend again.
const GUARD_STALE_TIME_MS = 10_000

/**
 * Route guard for `beforeLoad`: lets the navigation through only if the
 * current user may open the page. It runs before the page renders, so a
 * refused user does not see the page and its data is not requested.
 *
 * It can be up to GUARD_STALE_TIME_MS behind a change made elsewhere. In that
 * window the page's own request is refused by the backend, which shows the
 * same Forbidden page.
 */
export const requireRouteAccess = async (
  queryClient: QueryClient,
  route: GuardedRoute,
): Promise<void> => {
  const user = await queryClient.query({
    ...currentUserQueryOptions,
    staleTime: GUARD_STALE_TIME_MS,
    retry: false,
  })
  if (!canOpenRoute(user, route)) {
    throw new ForbiddenError()
  }
}
