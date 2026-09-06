import type { Metadata } from 'next';
import { Download } from 'lucide-react';
import { PageHeader } from '@/components/page-header';
import { ProductTable } from '@/components/products/product-table';
import { getCompetitors } from '@/lib/api/competitors';
import { getProducts } from '@/lib/api/products';

export const metadata: Metadata = { title: 'Products' };

const validFilters = [
  'all',
  'overpriced',
  'cheapest',
  'dropped',
  'increased',
  'out-of-stock',
  'stale',
] as const;

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string }>;
}) {
  const [products, competitorSummaries, params] = await Promise.all([
    getProducts(),
    getCompetitors(),
    searchParams,
  ]);
  const initialFilter = validFilters.includes(
    params.filter as (typeof validFilters)[number],
  )
    ? (params.filter as (typeof validFilters)[number])
    : 'all';
  return (
    <>
      <PageHeader
        eyebrow="Catalog intelligence"
        title="Products"
        description="Compare your price and availability against every monitored competitor."
        actions={
          <button
            type="button"
            className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 text-sm font-medium text-slate-600 shadow-sm hover:bg-slate-50"
          >
            <Download className="size-4" />
            Export view
          </button>
        }
      />
      <ProductTable
        products={products}
        competitors={competitorSummaries.map(({ id, name }) => ({ id, name }))}
        initialFilter={initialFilter}
      />
    </>
  );
}
