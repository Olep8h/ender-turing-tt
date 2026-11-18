// Note: the `PrivateService` is only available when generating the client
// for local environments
import {
  LoginService,
  PrivateService,
  type Role,
  UsersService,
} from "../../src/client"
import { client } from "../../src/client/client.gen"
import { firstSuperuser, firstSuperuserPassword } from "../config.ts"

client.setConfig({
  baseURL: `${process.env.VITE_API_URL}`,
})

export const createUser = async ({
  email,
  password,
}: {
  email: string
  password: string
}) => {
  const response = await PrivateService.createUser({
    body: {
      email,
      password,
      is_verified: true,
      full_name: "Test User",
    },
  })
  return response.data
}

// The private endpoint only creates members, so the helpers below act the way
// an admin would: through the authenticated users API.
const adminHeaders = async () => {
  const { data: token } = await LoginService.loginAccessToken({
    body: { username: firstSuperuser, password: firstSuperuserPassword },
  })
  return { Authorization: `Bearer ${token.access_token}` }
}

export const createUserWithRole = async ({
  email,
  password,
  role,
}: {
  email: string
  password: string
  role: Role
}) => {
  const response = await UsersService.createUser({
    body: { email, password, role, is_active: true },
    headers: await adminHeaders(),
  })
  return response.data
}

export const setUserRole = async (userId: string, role: Role) => {
  await UsersService.updateUser({
    path: { user_id: userId },
    body: { role },
    headers: await adminHeaders(),
  })
}
