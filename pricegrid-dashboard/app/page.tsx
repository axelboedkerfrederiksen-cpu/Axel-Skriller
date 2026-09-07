import Link from 'next/link';
import {
  AlertCircle,
  ArrowRight,
  BadgeDollarSign,
  Boxes,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  RefreshCw,
  TrendingDown,
} from 'lucide-react';
import { EventFeed } from '@/components/event-feed';
import { MetricCard } from '@/components/metric-card';
import { PageHeader } from '@/components/page-header';
import { StatusBadge } from '@/components/status-badge';
import { getDashboardData } from '@/lib/api/dashboard';
import {
  formatCurrency,
  formatPercentage,
  formatRelativeTime,
} from '@/lib/calculations';

export default async function OverviewPage() {
  const data = await getDashboardData();
  const today = new Intl.DateTimeFormat('en-DK', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  }).format(new Date());
  return (
    <>
      <PageHeader
        eyebrow={today}
        title="Pricing overview"
        description="See where your prices stand, what changed, and which products need attention."
        actions={
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 shadow-sm">
            <RefreshCw className="size-4 text-emerald-500" />
            Updated {formatRelativeTime(data.freshness.lastSuccessfulUpdate)}
          </div>
        }
      />
      <section
        className="grid grid-cols-2 gap-3 xl:grid-cols-3 2xl:grid-cols-6"
        aria-label="Key pricing metrics"
      >
        <MetricCard
          label="Monitored products"
          value={data.totalProducts}
          helper={`${data.monitoredOffers} competitor offers`}
          icon={Boxes}
        />
        <MetricCard
          label="Price changes"
          value={data.priceChanges24h}
          helper="In the last 24 hours"
          icon={TrendingDown}
          tone="violet"
        />
        <MetricCard
          label="Priced too high"
          value={data.overpricedProducts}
          helper="Above the cheapest offer"
          icon={AlertCircle}
          tone="rose"
        />
        <MetricCard
          label="You're cheapest"
          value={data.cheapestProducts}
          helper="Best available price"
          icon={BadgeDollarSign}
          tone="emerald"
        />
        <MetricCard
          label="Stale or failed"
          value={data.staleOrFailed}
          helper="Offers need attention"
          icon={Clock3}
          tone="amber"
        />
        <MetricCard
          label="Data health"
          value={`${data.freshness.healthyPercentage}%`}
          helper="Monitors reporting normally"
          icon={CheckCircle2}
          tone="blue"
        />
      </section>
      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(340px,0.85fr)]">
        <section className="rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgb(15_23_42/3%)]">
          <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="font-semibold tracking-tight text-slate-900">
                Largest price gaps
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Products with the clearest pricing opportunity
              </p>
            </div>
            <Link
              href="/products?filter=overpriced"
              className="flex items-center gap-1.5 text-sm font-medium text-blue-600 hover:text-blue-700"
            >
              View all <ArrowRight className="size-4" />
            </Link>
          </div>
          <div className="hidden overflow-x-auto scrollbar-subtle sm:block">
            <table className="w-full min-w-[660px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/70 text-xs font-medium uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-5 py-3">Product</th>
                  <th className="px-4 py-3">Your price</th>
                  <th className="px-4 py-3">Cheapest</th>
                  <th className="px-4 py-3">Gap</th>
                  <th className="px-5 py-3 text-right">Position</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.largestGaps.map((item) => (
                  <tr
                    key={item.product.id}
                    className="group hover:bg-slate-50/60"
                  >
                    <td className="px-5 py-3.5">
                      <Link
                        href={`/products/${item.product.id}`}
                        className="font-medium text-slate-800 group-hover:text-blue-600"
                      >
                        {item.product.name}
                      </Link>
                      <span className="mt-0.5 block text-xs text-slate-400">
                        {item.product.sku}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-medium tabular-nums text-slate-800">
                      {formatCurrency(
                        item.customerPrice,
                        item.product.currency,
                      )}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="font-medium tabular-nums text-slate-800">
                        {formatCurrency(
                          item.cheapestPrice,
                          item.product.currency,
                        )}
                      </span>
                      <span className="mt-0.5 block text-xs text-slate-400">
                        {item.cheapestCompetitor?.competitorName}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="font-semibold tabular-nums text-rose-600">
                        +
                        {formatCurrency(
                          item.differenceAmount,
                          item.product.currency,
                        )}
                      </span>
                      <span className="ml-1.5 text-xs text-rose-500">
                        {formatPercentage(item.differencePercentage)}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                        #{item.customerRank} of{' '}
                        {item.competitorOffers.filter((offer) => offer.inStock)
                          .length + 1}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="divide-y divide-slate-100 px-5 sm:hidden">
            {data.largestGaps.map((item) => (
              <Link
                key={item.product.id}
                href={`/products/${item.product.id}`}
                className="flex items-center justify-between gap-4 py-4"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-slate-800">
                    {item.product.name}
                  </span>
                  <span className="mt-1 block text-xs text-slate-400">
                    {item.cheapestCompetitor?.competitorName} ·{' '}
                    {formatCurrency(item.cheapestPrice, item.product.currency)}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  <span className="block text-sm font-semibold tabular-nums text-rose-600">
                    +
                    {formatCurrency(
                      item.differenceAmount,
                      item.product.currency,
                    )}
                  </span>
                  <span className="mt-1 block text-xs text-rose-500">
                    {formatPercentage(item.differencePercentage)}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </section>
        <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/3%)]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold tracking-tight text-slate-900">
                Recent activity
              </h2>
              <p className="mt-0.5 text-xs text-slate-500">
                Important movements across your catalog
              </p>
            </div>
            <span className="mt-1 flex size-2.5 rounded-full bg-blue-500 ring-4 ring-blue-50" />
          </div>
          <div className="mt-4">
            <EventFeed events={data.recentEvents.slice(0, 5)} compact />
          </div>
        </section>
      </div>
      <section className="mt-6 overflow-hidden rounded-2xl bg-[#172033] text-white shadow-[0_12px_30px_rgb(15_23_42/10%)]">
        <div className="grid items-center gap-6 px-5 py-5 sm:grid-cols-[auto_1fr_auto] sm:px-6">
          <span className="grid size-11 place-items-center rounded-2xl bg-emerald-400/15 text-emerald-300">
            <CircleDollarSign className="size-5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold">
                {data.freshness.status === 'healthy'
                  ? 'Pricing data is current'
                  : 'Some pricing data needs attention'}
              </h2>
              <StatusBadge
                status={data.freshness.status}
                className="border-emerald-400/20 bg-emerald-400/10 text-emerald-300"
              />
            </div>
            <p className="mt-1 text-sm text-slate-400">
              {data.freshness.checkedLastHour} of {data.monitoredOffers} offers
              checked in the last hour. A small number are queued for refresh.
            </p>
          </div>
          <Link
            href="/monitoring"
            className="flex items-center gap-2 text-sm font-medium text-blue-300 hover:text-blue-200"
          >
            Open monitoring <ArrowRight className="size-4" />
          </Link>
        </div>
      </section>
    </>
  );
}
