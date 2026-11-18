import type { Role } from "@/client"

// Display only. Access decisions go through hasPermission, never through a role.
export const roleLabels: Record<Role, string> = {
  admin: "Admin",
  manager: "Manager",
  member: "Member",
}

export const roles = Object.keys(roleLabels) as Role[]
