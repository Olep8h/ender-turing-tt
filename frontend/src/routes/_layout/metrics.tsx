import { useSuspenseQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Suspense } from "react"

import { MetricsService } from "@/client"
import { ForbiddenBoundary } from "@/components/Common/Forbidden"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { requireRouteAccess } from "@/lib/permissions"

function getMetricsQueryOptions() {
  return {
    queryFn: async () => (await MetricsService.readMetrics()).data,
    queryKey: ["metrics"],
  }
}

export const Route = createFileRoute("/_layout/metrics")({
  component: Metrics,
  beforeLoad: ({ context }) =>
    requireRouteAccess(context.queryClient, "/metrics"),
  errorComponent: ForbiddenBoundary,
  head: () => ({
    meta: [
      {
        title: "Metrics - FastAPI Template",
      },
    ],
  }),
})

function MetricsContent() {
  const { data: metrics } = useSuspenseQuery(getMetricsQueryOptions())

  const tiles = [
    { title: "Total users", value: metrics.total_users },
    { title: "Active users", value: metrics.active_users },
    { title: "Total items", value: metrics.total_items },
  ]

  return (
    <div className="grid gap-4 md:grid-cols-3">
      {tiles.map((tile) => (
        <Card key={tile.title}>
          <CardHeader>
            <CardTitle>{tile.title}</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-bold">{tile.value}</CardContent>
        </Card>
      ))}
    </div>
  )
}

function Metrics() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Metrics</h1>
        <p className="text-muted-foreground">Usage at a glance</p>
      </div>
      <Suspense fallback={<Skeleton className="h-28 w-full" />}>
        <MetricsContent />
      </Suspense>
    </div>
  )
}
