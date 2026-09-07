'use client';

import { AlertTriangle, RefreshCw } from 'lucide-react';

export default function ErrorState({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="grid min-h-[65vh] place-items-center text-center">
      <div>
        <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-rose-50 text-rose-600">
          <AlertTriangle className="size-6" />
        </span>
        <h1 className="mt-5 text-xl font-semibold text-slate-900">
          We couldn’t load this view
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          The pricing service may be temporarily unavailable.
        </p>
        <button
          type="button"
          onClick={reset}
          className="mt-5 inline-flex h-10 items-center gap-2 rounded-xl bg-slate-900 px-4 text-sm font-medium text-white"
        >
          <RefreshCw className="size-4" />
          Try again
        </button>
      </div>
    </div>
  );
}
