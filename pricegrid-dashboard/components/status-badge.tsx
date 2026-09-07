import { AlertTriangle, CheckCircle2, Clock3, XCircle } from 'lucide-react';
import type { MonitorStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

const styles = {
  healthy: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  stale: 'border-amber-200 bg-amber-50 text-amber-700',
  failed: 'border-rose-200 bg-rose-50 text-rose-700',
};
const labels = { healthy: 'Healthy', stale: 'Stale', failed: 'Failed' };

export function StatusBadge({
  status,
  className,
}: {
  status: MonitorStatus;
  className?: string;
}) {
  const Icon =
    status === 'healthy' ? CheckCircle2 : status === 'stale' ? Clock3 : XCircle;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        styles[status],
        className,
      )}
    >
      <Icon className="size-3.5" />
      {labels[status]}
    </span>
  );
}

export function StockBadge({ inStock }: { inStock: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-sm font-medium',
        inStock ? 'text-emerald-700' : 'text-slate-500',
      )}
    >
      {inStock ? (
        <CheckCircle2 className="size-4" />
      ) : (
        <AlertTriangle className="size-4 text-amber-500" />
      )}
      {inStock ? 'In stock' : 'Out of stock'}
    </span>
  );
}
