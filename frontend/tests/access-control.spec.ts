import { expect, test } from "@playwright/test"
import { createUser, createUserWithRole, setUserRole } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInUser } from "./utils/user"

test.use({ storageState: { cookies: [], origins: [] } })

test("Manager sees users without manage controls and can open metrics", async ({
  page,
}) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUserWithRole({ email, password, role: "manager" })
  await logInUser(page, email, password)

  await page.getByRole("link", { name: "Admin" }).click()

  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible()
  await expect(page.getByRole("row").filter({ hasText: email })).toBeVisible()
  await expect(page.getByRole("button", { name: "Add User" })).toHaveCount(0)
  // No row has an actions menu
  await expect(page.getByRole("row").getByRole("button")).toHaveCount(0)

  await page.getByRole("link", { name: "Metrics" }).click()

  await expect(page.getByRole("heading", { name: "Metrics" })).toBeVisible()
  await expect(page.getByText("Total users")).toBeVisible()
})

test("Member is refused on the metrics page before any data is requested", async ({
  page,
}) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  await logInUser(page, email, password)
  const metricsRequests: string[] = []
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/metrics")) {
      metricsRequests.push(request.url())
    }
  })

  await page.goto("/metrics")

  await expect(page.getByTestId("forbidden")).toBeVisible()
  await expect(page).toHaveURL(/\/metrics$/)
  await expect(page.getByRole("heading", { name: "Metrics" })).toHaveCount(0)
  expect(metricsRequests).toEqual([])
  // The refusal is shown inside the app layout, with the navigation still there
  await expect(page.getByRole("link", { name: "Items" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Metrics" })).toHaveCount(0)
})

test("Admin demoted mid-session is refused on their next change and sees Forbidden", async ({
  page,
}) => {
  const email = randomEmail()
  const password = randomPassword()
  const admin = await createUserWithRole({ email, password, role: "admin" })
  await logInUser(page, email, password)
  await page.getByRole("link", { name: "Admin" }).click()
  // The table re-reads the current user when it appears. Let that finish, so
  // that the page can only learn about the demotion from the refused request.
  await expect(page.getByRole("row").filter({ hasText: email })).toBeVisible()
  await page.waitForLoadState("networkidle")
  await page.getByRole("button", { name: "Add User" }).click()
  await page.getByPlaceholder("Email").fill(randomEmail())
  await page.getByPlaceholder("Password").first().fill(password)
  await page.getByPlaceholder("Password").last().fill(password)

  await setUserRole(admin.id, "member")

  const createRefused = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/users/" &&
      response.request().method() === "POST" &&
      response.status() === 403,
  )
  await page.getByRole("button", { name: "Save" }).click()
  await createRefused

  await expect(page.getByTestId("forbidden")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Users" })).toHaveCount(0)
  // Still inside the app layout, with the navigation of the new role
  await expect(page.getByRole("link", { name: "Items" })).toBeVisible()
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0)
})
