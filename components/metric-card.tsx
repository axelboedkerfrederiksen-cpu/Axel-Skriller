import type { LucideIcon } from 'lucide-react';

export function MetricCard({
  label,
  value,
  helper,
  icon: Icon,
  tone = 'blue',
}: {
  label: string;
  value: string | number;
  helper: string;
  icon: LucideIcon;
  tone?: 'blue' | 'amber' | 'emerald' | 'rose' | 'violet' | 'slate';
}) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    amber: 'bg-amber-50 text-amber-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    rose: 'bg-rose-50 text-rose-600',
    violet: 'bg-violet-50 text-violet-600',
    slate: 'bg-slate-100 text-slate-600',
  };
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-[0_1px_2px_rgb(15_23_42/3%)] sm:p-5">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-medium leading-5 text-slate-500">{label}</p>
        <span
          className={`grid size-9 shrink-0 place-items-center rounded-xl ${colors[tone]}`}
        >
          <Icon className="size-[18px]" />
        </span>
      </div>
      <p className="mt-4 text-[1.7rem] font-semibold leading-none tracking-[-0.04em] text-slate-950 tabular-nums">
        {value}
      </p>
      <p className="mt-2 text-xs text-slate-400">{helper}</p>
    </div>
  );
}
