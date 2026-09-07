import type { Metadata } from 'next';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Radio,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { MetricCard } from '@/components/metric-card';
import { PageHeader } from '@/components/page-header';
import { StatusBadge } from '@/components/status-badge';
import { Progress } from '@/components/ui/progress';
import { getHealth } from '@/lib/api/health';
import { formatRelativeTime } from '@/lib/calculations';

export const metadata: Metadata = { title: 'Monitoring' };

export default async function MonitoringPage() {
  const health = await getHealth();
  const healthyPercentage = health.totalMonitors
    ? Math.round((health.healthyMonitors / health.totalMonitors) * 100)
    : 0;
  return (
    <>
      <PageHeader
        eyebrow="Data freshness"
        title="Monitoring health"
        description="A clear view of which competitor prices are current and which checks need attention."
        actions={
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-50"
          >
            <RefreshCw className="size-4" />
            Check now
          </button>
        }
      />
      <section className="mb-6 overflow-hidden rounded-2xl bg-[#172033] text-white">
        <div className="grid gap-5 px-5 py-6 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:px-6">
          <span className="grid size-12 place-items-center rounded-2xl bg-emerald-400/15 text-emerald-300">
            <Radio className="size-5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">
                Monitoring is operational
              </h2>
              <span className="rounded-full bg-emerald-400/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
                {healthyPercentage}% healthy
              </span>
            </div>
            <p className="mt-1.5 text-sm text-slate-400">
              Most price checks are current.{' '}
              {health.staleMonitors + health.failedChecks} offers are awaiting a
              successful refresh.
            </p>
          </div>
          <div className="text-left sm:text-right">
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Last successful update
            </p>
            <p className="mt-1 text-sm font-medium text-slate-200">
              {formatRelativeTime(health.lastSuccessfulUpdate)}
            </p>
          </div>
        </div>
      </section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Healthy monitors"
          value={health.healthyMonitors}
          helper={`${healthyPercentage}% of all offers`}
          icon={CheckCircle2}
          tone="emerald"
        />
        <MetricCard
          label="Stale monitors"
          value={health.staleMonitors}
          helper="Older than expected"
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Failed checks"
          value={health.failedChecks}
          helper="Waiting for next attempt"
          icon={XCircle}
          tone="rose"
        />
        <MetricCard
          label="Total monitors"
          value={health.totalMonitors}
          helper="Competitor product pages"
          icon={Radio}
          tone="blue"
        />
      </section>
      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold tracking-tight text-slate-900">
            Site status
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Current monitoring health for each competitor.
          </p>
        </div>
        <div className="divide-y divide-slate-100">
          {health.sites.map((site) => {
            const total =
              site.healthyMonitors + site.staleMonitors + site.failedChecks;
            const percentage = total
              ? Math.round((site.healthyMonitors / total) * 100)
              : 0;
            return (
              <article
                key={site.id}
                className="grid gap-4 p-5 md:grid-cols-[minmax(180px,1.1fr)_minmax(250px,1.5fr)_repeat(3,minmax(80px,.55fr))_minmax(130px,.8fr)] md:items-center"
              >
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-slate-600">
                    {site.name.slice(0, 2).toUpperCase()}
                  </span>
                  <div>
                    <h3 className="font-semibold text-slate-850">
                      {site.name}
                    </h3>
                    <div className="mt-1">
                      <StatusBadge status={site.status} />
                    </div>
                  </div>
                </div>
                <div>
                  <div className="mb-2 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-600">
                      {percentage}% reporting normally
                    </span>
                    <span className="text-slate-400">
                      {site.healthyMonitors} / {total}
                    </span>
                  </div>
                  <Progress
                    value={percentage}
                    className="[&_[data-slot=progress-indicator]]:bg-emerald-500"
                  />
                </div>
                <div>
                  <p className="text-xs text-slate-400">Healthy</p>
                  <p className="mt-1 flex items-center gap-1.5 font-semibold tabular-nums text-slate-800">
                    <CheckCircle2 className="size-4 text-emerald-500" />
                    {site.healthyMonitors}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Stale</p>
                  <p className="mt-1 flex items-center gap-1.5 font-semibold tabular-nums text-slate-800">
                    <Clock3 className="size-4 text-amber-500" />
                    {site.staleMonitors}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Failed</p>
                  <p className="mt-1 flex items-center gap-1.5 font-semibold tabular-nums text-slate-800">
                    <AlertTriangle className="size-4 text-rose-500" />
                    {site.failedChecks}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">
                    Last successful update
                  </p>
                  <p className="mt-1 text-sm font-medium text-slate-700">
                    {formatRelativeTime(site.lastSuccessfulUpdate)}
                  </p>
                </div>
              </article>
            );
          })}
        </div>
      </section>
      <aside className="mt-6 rounded-2xl border border-blue-100 bg-blue-50/70 p-5">
        <div className="flex gap-3">
          <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-blue-100 text-blue-600">
            <RefreshCw className="size-4" />
          </span>
          <div>
            <h2 className="text-sm font-semibold text-blue-950">
              What happens next?
            </h2>
            <p className="mt-1 text-sm leading-6 text-blue-800/75">
              Stale and failed checks are retried automatically. Your current
              pricing data remains visible while a fresh result is being
              collected.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
