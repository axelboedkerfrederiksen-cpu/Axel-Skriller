'use client';

import Link from 'next/link';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronRight,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { StatusBadge, StockBadge } from '@/components/status-badge';
import {
  formatCurrency,
  formatPercentage,
  formatRelativeTime,
} from '@/lib/calculations';
import type { Competitor, ProductComparison } from '@/lib/types';
import { cn } from '@/lib/utils';

type FilterKey =
  | 'all'
  | 'overpriced'
  | 'cheapest'
  | 'dropped'
  | 'increased'
  | 'out-of-stock'
  | 'stale';
type SortKey =
  | 'product'
  | 'customerPrice'
  | 'cheapestPrice'
  | 'differenceAmount'
  | 'differencePercentage'
  | 'customerRank'
  | 'lastChecked';
type SortDirection = 'asc' | 'desc';

const filterOptions: { value: FilterKey; label: string }[] = [
  { value: 'all', label: 'All products' },
  { value: 'overpriced', label: 'Overpriced' },
  { value: 'cheapest', label: 'You’re cheapest' },
  { value: 'dropped', label: 'Competitor dropped' },
  { value: 'increased', label: 'Competitor increased' },
  { value: 'out-of-stock', label: 'Out of stock' },
  { value: 'stale', label: 'Stale data' },
];

function matchesFilter(item: ProductComparison, filter: FilterKey) {
  if (filter === 'overpriced') return (item.differenceAmount ?? 0) > 0;
  if (filter === 'cheapest') return item.isCustomerCheapest === true;
  if (filter === 'dropped') return item.hasRecentCompetitorDrop;
  if (filter === 'increased') return item.hasRecentCompetitorIncrease;
  if (filter === 'out-of-stock')
    return (
      item.product.inStock === false ||
      item.competitorOffers.some((offer) => offer.inStock === false)
    );
  if (filter === 'stale') return item.status !== 'healthy';
  return true;
}

function SortButton({
  label,
  sortKey,
  activeKey,
  direction,
  onSort,
  align = 'left',
}: {
  label: string;
  sortKey: SortKey;
  activeKey: SortKey;
  direction: SortDirection;
  onSort: (key: SortKey) => void;
  align?: 'left' | 'right';
}) {
  const Icon =
    activeKey !== sortKey
      ? ArrowUpDown
      : direction === 'asc'
        ? ArrowUp
        : ArrowDown;
  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn(
        'inline-flex w-full items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400 hover:text-slate-700',
        align === 'right' && 'justify-end',
      )}
    >
      <span>{label}</span>
      <Icon className="size-3.5" />
    </button>
  );
}

export function ProductTable({
  products,
  competitors,
  initialFilter = 'all',
}: {
  products: ProductComparison[];
  competitors: Competitor[];
  initialFilter?: FilterKey;
}) {
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<FilterKey>(initialFilter);
  const [competitorId, setCompetitorId] = useState('all');
  const [sortKey, setSortKey] = useState<SortKey>('differenceAmount');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  const visibleProducts = useMemo(() => {
    const normalized = search.trim().toLowerCase();
    const filtered = products.filter((item) => {
      const matchesSearch =
        !normalized ||
        `${item.product.name} ${item.product.sku}`
          .toLowerCase()
          .includes(normalized);
      const matchesCompetitor =
        competitorId === 'all' ||
        item.competitorOffers.some(
          (offer) => offer.competitorId === competitorId,
        );
      return matchesSearch && matchesCompetitor && matchesFilter(item, filter);
    });
    return [...filtered].sort((a, b) => {
      const valueA: string | number =
        sortKey === 'product'
          ? a.product.name
          : sortKey === 'lastChecked'
            ? new Date(a.product.lastChecked).getTime()
            : (a[sortKey] ?? Number.NEGATIVE_INFINITY);
      const valueB: string | number =
        sortKey === 'product'
          ? b.product.name
          : sortKey === 'lastChecked'
            ? new Date(b.product.lastChecked).getTime()
            : (b[sortKey] ?? Number.NEGATIVE_INFINITY);
      if (typeof valueA === 'string' && typeof valueB === 'string')
        return (
          (sortDirection === 'asc' ? 1 : -1) * valueA.localeCompare(valueB)
        );
      return (
        (sortDirection === 'asc' ? 1 : -1) * (Number(valueA) - Number(valueB))
      );
    });
  }, [competitorId, filter, products, search, sortDirection, sortKey]);

  useEffect(() => {
    const context =
      typeof document === 'undefined' ? undefined : document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(
      context.registerTool(
        {
          name: 'filter_products',
          title: 'Filter monitored products',
          description:
            'Filter the visible product comparison table by pricing status, competitor, or search text.',
          inputSchema: {
            type: 'object',
            properties: {
              filter: {
                type: 'string',
                enum: filterOptions.map((option) => option.value),
              },
              competitorId: { type: 'string' },
              search: { type: 'string' },
            },
            additionalProperties: false,
          },
          annotations: { readOnlyHint: true, untrustedContentHint: false },
          execute(input: unknown) {
            const value = input as {
              filter?: FilterKey;
              competitorId?: string;
              search?: string;
            };
            if (
              value.filter &&
              !filterOptions.some((option) => option.value === value.filter)
            )
              throw new Error('Unknown product filter.');
            if (
              value.competitorId &&
              value.competitorId !== 'all' &&
              !competitors.some(
                (competitor) => competitor.id === value.competitorId,
              )
            )
              throw new Error('Unknown competitor.');
            if (value.filter) setFilter(value.filter);
            if (value.competitorId) setCompetitorId(value.competitorId);
            if (typeof value.search === 'string') setSearch(value.search);
            return {
              status: 'applied',
              filter: value.filter ?? filter,
              competitorId: value.competitorId ?? competitorId,
              search: value.search ?? search,
            };
          },
        },
        { signal: lifecycle.signal },
      ),
    ).catch(() => undefined);
    return () => lifecycle.abort();
  }, [competitorId, competitors, filter, search]);

  function handleSort(key: SortKey) {
    if (sortKey === key)
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
    else {
      setSortKey(key);
      setSortDirection(key === 'product' ? 'asc' : 'desc');
    }
  }

  const activeFilters =
    Number(filter !== 'all') +
    Number(competitorId !== 'all') +
    Number(Boolean(search));

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-[0_1px_2px_rgb(15_23_42/3%)]">
      <div className="border-b border-slate-100 p-4 sm:p-5">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="relative w-full xl:max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search product or SKU"
              className="h-10 rounded-xl bg-slate-50 pl-9"
              aria-label="Search products"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SlidersHorizontal className="mr-1 size-4 text-slate-400" />
            <Select
              value={filter}
              onValueChange={(value) => setFilter(value as FilterKey)}
            >
              <SelectTrigger className="h-10 min-w-44 rounded-xl bg-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {filterOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={competitorId}
              onValueChange={(value) => setCompetitorId(value as string)}
            >
              <SelectTrigger className="h-10 min-w-44 rounded-xl bg-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All competitors</SelectItem>
                {competitors.map((competitor) => (
                  <SelectItem key={competitor.id} value={competitor.id}>
                    {competitor.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activeFilters > 0 && (
              <button
                type="button"
                onClick={() => {
                  setSearch('');
                  setFilter('all');
                  setCompetitorId('all');
                }}
                className="inline-flex h-10 items-center gap-1.5 rounded-xl px-3 text-sm font-medium text-slate-500 hover:bg-slate-50 hover:text-slate-800"
              >
                <X className="size-4" />
                Clear
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between">
          <p className="text-sm text-slate-500">
            <span className="font-medium text-slate-800">
              {visibleProducts.length}
            </span>{' '}
            of {products.length} products
          </p>
          {activeFilters > 0 && (
            <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
              {activeFilters} active{' '}
              {activeFilters === 1 ? 'filter' : 'filters'}
            </span>
          )}
        </div>
      </div>
      {visibleProducts.length ? (
        <div className="overflow-x-auto scrollbar-subtle">
          <Table className="min-w-[1240px]">
            <TableHeader>
              <TableRow className="border-slate-100 bg-slate-50/70 hover:bg-slate-50/70">
                <TableHead className="h-11 px-5">
                  <SortButton
                    label="Product"
                    sortKey="product"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortButton
                    label="Your price"
                    sortKey="customerPrice"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>Cheapest competitor</TableHead>
                <TableHead>
                  <SortButton
                    label="Cheapest price"
                    sortKey="cheapestPrice"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortButton
                    label="Difference"
                    sortKey="differenceAmount"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortButton
                    label="Difference %"
                    sortKey="differencePercentage"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>
                  <SortButton
                    label="Position"
                    sortKey="customerRank"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead>Stock</TableHead>
                <TableHead>Competitors</TableHead>
                <TableHead>
                  <SortButton
                    label="Last checked"
                    sortKey="lastChecked"
                    activeKey={sortKey}
                    direction={sortDirection}
                    onSort={handleSort}
                  />
                </TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleProducts.map((item) => {
                const positiveGap = (item.differenceAmount ?? 0) > 0;
                return (
                  <TableRow
                    key={item.product.id}
                    className="group border-slate-100"
                  >
                    <TableCell className="px-5 py-3.5">
                      <Link
                        href={`/products/${item.product.id}`}
                        className="block max-w-[260px]"
                      >
                        <span className="block truncate font-medium text-slate-850 group-hover:text-blue-600">
                          {item.product.name}
                        </span>
                        <span className="mt-1 block text-xs text-slate-400">
                          {item.product.sku}
                        </span>
                      </Link>
                    </TableCell>
                    <TableCell className="font-semibold tabular-nums text-slate-800">
                      {formatCurrency(
                        item.customerPrice,
                        item.product.currency,
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="font-medium text-slate-700">
                        {item.cheapestCompetitor?.competitorName ?? '—'}
                      </span>
                      {item.hasRecentCompetitorDrop && (
                        <span className="mt-1 flex items-center gap-1 text-xs font-medium text-emerald-600">
                          <ArrowDown className="size-3" />
                          Dropped recently
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="font-medium tabular-nums text-slate-700">
                      {formatCurrency(
                        item.cheapestPrice,
                        item.product.currency,
                      )}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'font-semibold tabular-nums',
                        positiveGap ? 'text-rose-600' : 'text-emerald-600',
                      )}
                    >
                      {formatCurrency(
                        item.differenceAmount,
                        item.product.currency,
                      )}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'font-semibold tabular-nums',
                        positiveGap ? 'text-rose-600' : 'text-emerald-600',
                      )}
                    >
                      {formatPercentage(item.differencePercentage)}
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex min-w-14 justify-center rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
                        {item.customerRank === null
                          ? '—'
                          : `#${item.customerRank}`}{' '}
                        /{' '}
                        {item.competitorOffers.filter(
                          (offer) => offer.inStock === true,
                        ).length + 1}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StockBadge inStock={item.product.inStock} />
                    </TableCell>
                    <TableCell className="text-center font-medium tabular-nums text-slate-700">
                      {item.competitorOffers.length}
                    </TableCell>
                    <TableCell>
                      <span className="block text-sm text-slate-600">
                        {formatRelativeTime(item.product.lastChecked)}
                      </span>
                      {item.status !== 'healthy' && (
                        <StatusBadge status={item.status} className="mt-1" />
                      )}
                    </TableCell>
                    <TableCell>
                      <Link
                        href={`/products/${item.product.id}`}
                        aria-label={`View ${item.product.name}`}
                        className="grid size-8 place-items-center rounded-lg text-slate-400 hover:bg-blue-50 hover:text-blue-600"
                      >
                        <ChevronRight className="size-4" />
                      </Link>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="grid min-h-72 place-items-center p-8 text-center">
          <div>
            <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-400">
              <Search className="size-5" />
            </span>
            <h3 className="mt-4 font-semibold text-slate-800">
              No products found
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Try changing or clearing your filters.
            </p>
            <button
              type="button"
              onClick={() => {
                setSearch('');
                setFilter('all');
                setCompetitorId('all');
              }}
              className="mt-4 text-sm font-medium text-blue-600"
            >
              Clear all filters
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
