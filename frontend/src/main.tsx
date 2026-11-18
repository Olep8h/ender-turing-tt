import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
  type QueryKey,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { AxiosError } from "axios"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import type { UserMePublic } from "./client"
import { client } from "./client/client.gen"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import { currentUserQueryOptions } from "./lib/permissions"
import { routeTree } from "./routeTree.gen"

client.setConfig({
  baseURL: import.meta.env.VITE_API_URL ?? "",
  auth: () => localStorage.getItem("access_token") || "",
})

const statusOf = (error: Error) =>
  error instanceof AxiosError ? error.response?.status : undefined

const isCurrentUserQuery = (queryKey: QueryKey | undefined) =>
  queryKey?.[0] === currentUserQueryOptions.queryKey[0]

const handleApiError = (error: Error, failedQueryKey?: QueryKey) => {
  const status = statusOf(error)
  if (status === 401) {
    // The session is over: the token is invalid, or the user was deleted or
    // deactivated.
    localStorage.removeItem("access_token")
    window.location.href = "/login"
  } else if (status === 403 && !isCurrentUserQuery(failedQueryKey)) {
    // The user's access is not what this page assumed, typically because
    // their role changed while they had it open. Ask the backend who they are
    // now. The refused request itself is not retried.
    void queryClient.invalidateQueries({
      queryKey: currentUserQueryOptions.queryKey,
    })
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Asking again does not help when the answer is "not allowed"
      retry: (failureCount, error) =>
        ![401, 403].includes(statusOf(error) ?? 0) && failureCount < 3,
    },
  },
  queryCache: new QueryCache({
    onError: (error, query) => handleApiError(error, query.queryKey),
  }),
  mutationCache: new MutationCache({
    onError: (error) => handleApiError(error),
  }),
})

const router = createRouter({ routeTree, context: { queryClient } })

// The one mechanism that reacts to a change in the user's access. Whenever the
// current user's permissions in the cache change, however that was noticed,
// the route guards run again. While the permissions stay the same nothing
// happens, so a request that keeps being refused cannot start a loop.
let knownPermissions: string | undefined
queryClient.getQueryCache().subscribe(({ query }) => {
  const user = isCurrentUserQuery(query.queryKey)
    ? (query.state.data as UserMePublic | undefined)
    : undefined
  if (!user) {
    return
  }
  const permissions = String(user.permissions)
  if (knownPermissions !== undefined && permissions !== knownPermissions) {
    // A page that was refused under the old permissions must not stay refused
    // because of its cached error
    queryClient.removeQueries({
      type: "inactive",
      predicate: (cached) => cached.state.status === "error",
    })
    void router.invalidate()
  }
  knownPermissions = permissions
})

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
