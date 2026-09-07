import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  Clock3,
  ExternalLink,
  Medal,
  RefreshCw,
  Trophy,
} from 'lucide-react';
import { EventFeed } from '@/components/event-feed';
import { PriceHistoryChart } from '@/components/products/price-history-chart';
import { StatusBadge, StockBadge } from '@/components/status-badge';
import { getProductDetail } from '@/lib/api/products';
import {
  formatCurrency,
  formatPercentage,
  formatRelativeTime,
} from '@/lib/calculations';
import { cn } from '@/lib/utils';

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const detail = await getProductDetail(id);
  return { title: detail?.comparison.product.name ?? 'Product' };
}

export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const detail = await getProductDetail(id);
  if (!detail) notFound();
  const { comparison, history, events } = detail;
  const product = comparison.product;
  const availableOffers = comparison.competitorOffers.filter(
    (offer) => offer.inStock === true,
  );

  return (
    <>
      <Link
        href="/products"
        className="mb-5 inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-800"
      >
        <ArrowLeft className="size-4" />
        Back to products
      </Link>
      <div className="mb-6 flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-blue-600">
              {product.sku}
            </span>
            <StatusBadge status={comparison.status} />
          </div>
          <h1 className="text-2xl font-semibold tracking-[-0.035em] text-slate-950 sm:text-[1.75rem]">
            {product.name}
          </h1>
          <p className="mt-1.5 text-sm text-slate-500">
            Compared across {comparison.competitorOffers.length} competitors ·
            Last checked {formatRelativeTime(product.lastChecked)}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-medium text-white shadow-[0_8px_20px_rgb(37_99_235/20%)] hover:bg-blue-700"
        >
          <RefreshCw className="size-4" />
          Refresh prices
        </button>
      </div>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-sm font-medium text-slate-500">Your price</p>
          <p className="mt-3 text-2xl font-semibold tracking-tight tabular-nums text-slate-950">
            {formatCurrency(product.customerPrice, product.currency)}
          </p>
          <div className="mt-2">
            <StockBadge inStock={product.inStock} />
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-sm font-medium text-slate-500">
            Cheapest competitor
          </p>
          <p className="mt-3 text-2xl font-semibold tracking-tight tabular-nums text-slate-950">
            {formatCurrency(comparison.cheapestPrice, product.currency)}
          </p>
          <p className="mt-2 text-sm text-slate-500">
            {comparison.cheapestCompetitor?.competitorName ??
              'No available offer'}
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-sm font-medium text-slate-500">Price position</p>
          <div className="mt-3 flex items-center gap-2">
            <span className="text-2xl font-semibold tracking-tight text-slate-950">
              {comparison.customerRank === null
                ? '—'
                : `#${comparison.customerRank}`}
            </span>
            {comparison.customerRank === 1 ? (
              <Trophy className="size-5 text-amber-500" />
            ) : comparison.customerRank !== null ? (
              <Medal className="size-5 text-blue-500" />
            ) : null}
          </div>
          <p className="mt-2 text-sm text-slate-500">
            Out of {availableOffers.length + 1} available sellers
          </p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5">
          <p className="text-sm font-medium text-slate-500">Gap to cheapest</p>
          <p
            className={cn(
              'mt-3 flex items-center gap-1 text-2xl font-semibold tracking-tight tabular-nums',
              (comparison.differenceAmount ?? 0) > 0
                ? 'text-rose-600'
                : 'text-emerald-600',
            )}
          >
            {(comparison.differenceAmount ?? 0) > 0 ? (
              <ArrowUpRight className="size-5" />
            ) : (
              <ArrowDownLeft className="size-5" />
            )}
            {formatCurrency(
              Math.abs(comparison.differenceAmount ?? 0),
              product.currency,
            )}
          </p>
          <p className="mt-2 text-sm text-slate-500">
            {formatPercentage(comparison.differencePercentage)} versus market
            leader
          </p>
        </div>
      </section>

      <div className="mt-6 grid gap-6 2xl:grid-cols-[minmax(0,1.55fr)_minmax(330px,0.65fr)]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold tracking-tight text-slate-900">
                Price history
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Competitor history with your current price as a reference.
              </p>
            </div>
            <span className="rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-600">
              Last 21 days
            </span>
          </div>
          <PriceHistoryChart history={history} currency={product.currency} />
        </section>
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="mb-5">
            <h2 className="font-semibold tracking-tight text-slate-900">
              Price events
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Noteworthy changes for this product.
            </p>
          </div>
          <EventFeed events={events} />
        </section>
      </div>

      <section className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold tracking-tight text-slate-900">
            Current offers
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Live price and availability across monitored sites.
          </p>
        </div>
        <div className="overflow-x-auto scrollbar-subtle">
          <table className="w-full min-w-[800px] text-left text-sm">
            <thead className="border-b border-slate-100 bg-slate-50/70 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-5 py-3 font-medium">Seller</th>
                <th className="px-4 py-3 font-medium">Price</th>
                <th className="px-4 py-3 font-medium">Difference vs you</th>
                <th className="px-4 py-3 font-medium">Stock</th>
                <th className="px-4 py-3 font-medium">Last checked</th>
                <th className="px-5 py-3 font-medium text-right">
                  Product page
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr className="bg-blue-50/35">
                <th
                  scope="row"
                  aria-label="Your store"
                  className="px-5 py-4 text-left"
                >
                  <div className="flex items-center gap-3">
                    <span className="grid size-9 place-items-center rounded-xl bg-blue-600 text-xs font-bold text-white">
                      YOU
                    </span>
                    <div>
                      <span className="font-semibold text-slate-900">
                        Your store
                      </span>
                      <span className="mt-0.5 block text-xs text-blue-600">
                        Customer price
                      </span>
                    </div>
                  </div>
                </th>
                <td className="px-4 py-4 font-semibold tabular-nums text-slate-900">
                  {formatCurrency(product.customerPrice, product.currency)}
                </td>
                <td className="px-4 py-4 text-slate-400">—</td>
                <td className="px-4 py-4">
                  <StockBadge inStock={product.inStock} />
                </td>
                <td className="px-4 py-4 text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <Clock3 className="size-3.5" />
                    {formatRelativeTime(product.lastChecked)}
                  </span>
                </td>
                <td className="px-5 py-4">
                  <span className="sr-only">No external product page</span>
                </td>
              </tr>
              {[...comparison.competitorOffers]
                .sort(
                  (a, b) =>
                    (a.price ?? Number.POSITIVE_INFINITY) -
                    (b.price ?? Number.POSITIVE_INFINITY),
                )
                .map((offer) => {
                  const difference =
                    offer.price === null || product.customerPrice === null
                      ? null
                      : offer.price - product.customerPrice;
                  return (
                    <tr key={offer.id} className="hover:bg-slate-50/60">
                      <th
                        scope="row"
                        aria-label={offer.competitorName}
                        className="px-5 py-4 text-left"
                      >
                        <div className="flex items-center gap-3">
                          <span className="grid size-9 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-slate-600">
                            {offer.competitorName.slice(0, 2).toUpperCase()}
                          </span>
                          <div>
                            <span className="font-medium text-slate-800">
                              {offer.competitorName}
                            </span>
                            {comparison.cheapestCompetitor?.id === offer.id && (
                              <span className="mt-0.5 block text-xs font-medium text-emerald-600">
                                Cheapest competitor
                              </span>
                            )}
                          </div>
                        </div>
                      </th>
                      <td className="px-4 py-4 font-semibold tabular-nums text-slate-800">
                        {formatCurrency(offer.price, offer.currency)}
                      </td>
                      <td
                        className={cn(
                          'px-4 py-4 font-medium tabular-nums',
                          difference !== null && difference < 0
                            ? 'text-rose-600'
                            : 'text-emerald-600',
                        )}
                      >
                        {difference !== null && difference > 0 ? '+' : ''}
                        {formatCurrency(difference, product.currency)}
                      </td>
                      <td className="px-4 py-4">
                        <StockBadge inStock={offer.inStock} />
                      </td>
                      <td className="px-4 py-4">
                        <span className="text-slate-500">
                          {formatRelativeTime(offer.lastChecked)}
                        </span>
                        {offer.status !== 'healthy' && (
                          <StatusBadge status={offer.status} className="ml-2" />
                        )}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <a
                          href={offer.productUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 font-medium text-blue-600 hover:text-blue-700"
                        >
                          Open <ExternalLink className="size-3.5" />
                        </a>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
