import Link from 'next/link';
import { ArrowLeft, SearchX } from 'lucide-react';

export default function ProductNotFound() {
  return (
    <div className="grid min-h-[65vh] place-items-center text-center">
      <div>
        <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-100 text-slate-400">
          <SearchX className="size-6" />
        </span>
        <h1 className="mt-5 text-xl font-semibold text-slate-900">
          Product not found
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          This product may no longer be monitored.
        </p>
        <Link
          href="/products"
          className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-blue-600"
        >
          <ArrowLeft className="size-4" />
          Return to products
        </Link>
      </div>
    </div>
  );
}
