import type { Metadata } from 'next';
import { Activity, BarChart3, CheckCircle2, Clock3, Store } from 'lucide-react';
import { MetricCard } from '@/components/metric-card';
import { PageHeader } from '@/components/page-header';
import { StatusBadge } from '@/components/status-badge';
import { Progress } from '@/components/ui/progress';
import { getCompetitors } from '@/lib/api/competitors';
import { formatPercentage, formatRelativeTime } from '@/lib/calculations';
import { cn } from '@/lib/utils';

export const metadata: Metadata = { title: 'Competitors' };

export default async function CompetitorsPage() {
  const competitors = await getCompetitors();
  const totalOffers = competitors.reduce(
    (sum, competitor) => sum + competitor.monitoredProducts,
    0,
  );
  const totalCheapest = competitors.reduce(
    (sum, competitor) => sum + competitor.cheapestProducts,
    0,
  );
  const healthy = competitors.filter(
    (competitor) => competitor.status === 'healthy',
  ).length;
  const averageSuccess = Math.round(
    competitors.reduce((sum, competitor) => sum + competitor.successRate, 0) /
      competitors.length,
  );
  return (
    <>
      <PageHeader
        eyebrow="Market coverage"
        title="Competitors"
        description="Compare coverage, price position, and data quality across monitored sites."
      />
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Competitors"
          value={competitors.length}
          helper="Active monitored sites"
          icon={Store}
        />
        <MetricCard
          label="Competitor offers"
          value={totalOffers}
          helper="Across your catalog"
          icon={BarChart3}
          tone="violet"
        />
        <MetricCard
          label="Market-leading offers"
          value={totalCheapest}
          helper="Cheapest available positions"
          icon={Activity}
          tone="amber"
        />
        <MetricCard
          label="Average success rate"
          value={`${averageSuccess}%`}
          helper={`${healthy} sites fully healthy`}
          icon={CheckCircle2}
          tone="emerald"
        />
      </section>
      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold tracking-tight text-slate-900">
            Competitor performance
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Price position and monitoring reliability by site.
          </p>
        </div>
        <div className="overflow-x-auto scrollbar-subtle">
          <table className="w-full min-w-[880px] text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/70 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-5 py-3 font-medium">Competitor</th>
                <th className="px-4 py-3 font-medium">Monitored products</th>
                <th className="px-4 py-3 font-medium">Avg. price vs you</th>
                <th className="px-4 py-3 font-medium">Cheapest on</th>
                <th className="px-4 py-3 font-medium">Data reliability</th>
                <th className="px-4 py-3 font-medium">
                  Last successful scrape
                </th>
                <th className="px-5 py-3 text-right font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {competitors.map((competitor) => (
                <tr key={competitor.id} className="hover:bg-slate-50/60">
                  <th
                    scope="row"
                    aria-label={competitor.name}
                    className="px-5 py-4 text-left"
                  >
                    <div className="flex items-center gap-3">
                      <span className="grid size-10 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-slate-600">
                        {competitor.name.slice(0, 2).toUpperCase()}
                      </span>
                      <span className="font-semibold text-slate-850">
                        {competitor.name}
                      </span>
                    </div>
                  </th>
                  <td className="px-4 py-4 font-medium tabular-nums text-slate-700">
                    {competitor.monitoredProducts}
                  </td>
                  <td
                    className={cn(
                      'px-4 py-4 font-semibold tabular-nums',
                      competitor.averageDifferencePercentage < 0
                        ? 'text-rose-600'
                        : 'text-emerald-600',
                    )}
                  >
                    {formatPercentage(competitor.averageDifferencePercentage)}
                  </td>
                  <td className="px-4 py-4">
                    <span className="font-semibold tabular-nums text-slate-800">
                      {competitor.cheapestProducts}
                    </span>
                    <span className="text-slate-400"> products</span>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex min-w-32 items-center gap-3">
                      <Progress
                        value={competitor.successRate}
                        className="flex-1 [&_[data-slot=progress-indicator]]:bg-emerald-500"
                      />
                      <span className="w-9 text-right text-xs font-medium tabular-nums text-slate-600">
                        {competitor.successRate}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-slate-500">
                    <span className="flex items-center gap-1.5">
                      <Clock3 className="size-3.5" />
                      {formatRelativeTime(competitor.lastSuccessfulScrape)}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-right">
                    <StatusBadge status={competitor.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {competitors.map((competitor, index) => (
          <article
            key={competitor.id}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    'grid size-10 place-items-center rounded-xl text-xs font-bold',
                    [
                      'bg-blue-50 text-blue-600',
                      'bg-violet-50 text-violet-600',
                      'bg-amber-50 text-amber-600',
                      'bg-cyan-50 text-cyan-600',
                    ][index],
                  )}
                >
                  {competitor.name.slice(0, 2).toUpperCase()}
                </span>
                <div>
                  <h3 className="font-semibold text-slate-900">
                    {competitor.name}
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {competitor.monitoredProducts} monitored products
                  </p>
                </div>
              </div>
              <StatusBadge status={competitor.status} />
            </div>
            <div className="mt-5 grid grid-cols-3 divide-x divide-slate-100 rounded-xl bg-slate-50 p-3 text-center">
              <div>
                <p className="text-lg font-semibold tabular-nums text-slate-900">
                  {competitor.cheapestProducts}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">Cheapest</p>
              </div>
              <div>
                <p className="text-lg font-semibold tabular-nums text-slate-900">
                  {formatPercentage(competitor.averageDifferencePercentage)}
                </p>
                <p className="mt-0.5 text-xs text-slate-500">Avg. difference</p>
              </div>
              <div>
                <p className="text-lg font-semibold tabular-nums text-slate-900">
                  {competitor.successRate}%
                </p>
                <p className="mt-0.5 text-xs text-slate-500">Success rate</p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
