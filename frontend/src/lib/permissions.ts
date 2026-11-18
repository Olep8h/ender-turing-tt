import type { Permission, UserMePublic } from "@/client"

/**
 * The one place where the frontend decides what the current user may do.
 *
 * The permissions arrive from the backend with the current user, so the rules
 * for which role may do what exist only in the backend policy.
 */
export const hasPermission = (
  user: UserMePublic | null | undefined,
  permission: Permission,
): boolean => user?.permissions.includes(permission) ?? false
