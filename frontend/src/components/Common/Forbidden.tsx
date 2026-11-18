import { type ErrorComponentProps, Link } from "@tanstack/react-router"
import { AxiosError } from "axios"

import { Button } from "@/components/ui/button"
import { ForbiddenError } from "@/lib/permissions"

const Forbidden = () => {
  return (
    <div
      className="flex flex-col items-center justify-center gap-4 py-12 text-center"
      data-testid="forbidden"
    >
      <h1 className="text-2xl font-bold tracking-tight">Access denied</h1>
      <p className="text-muted-foreground">
        You don't have permission to view this page.
      </p>
      <Link to="/">
        <Button>Go to dashboard</Button>
      </Link>
    </div>
  )
}

const isForbidden = (error: unknown) =>
  error instanceof ForbiddenError ||
  (error instanceof AxiosError && error.response?.status === 403)

/**
 * `errorComponent` for guarded routes. A refusal, from the route guard or from
 * the API while the page is open, shows the Forbidden page inside the layout.
 * Any other error is passed on to the app's error page.
 */
export const ForbiddenBoundary = ({ error }: ErrorComponentProps) => {
  if (!isForbidden(error)) {
    throw error
  }
  return <Forbidden />
}

export default Forbidden
