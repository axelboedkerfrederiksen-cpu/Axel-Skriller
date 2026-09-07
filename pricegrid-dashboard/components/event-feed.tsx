import Link from 'next/link';
import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  PackageCheck,
  PackageX,
} from 'lucide-react';
import { formatCurrency, formatRelativeTime } from '@/lib/calculations';
import type { PriceChangeEvent } from '@/lib/types';

function eventCopy(event: PriceChangeEvent) {
  const source = event.competitorName ?? 'Your store';
  if (event.eventType === 'price_drop')
    return `${source} lowered the price from ${formatCurrency(event.oldPrice ?? null)} to ${formatCurrency(event.newPrice ?? null)}`;
  if (event.eventType === 'price_increase')
    return `${source} raised the price from ${formatCurrency(event.oldPrice ?? null)} to ${formatCurrency(event.newPrice ?? null)}`;
  if (event.eventType === 'out_of_stock') return `${source} went out of stock`;
  if (event.eventType === 'back_in_stock') return `${source} is back in stock`;
  return 'Your store became the cheapest option';
}

function EventIcon({ type }: { type: PriceChangeEvent['eventType'] }) {
  const config = {
    price_drop: {
      icon: ArrowDownRight,
      style: 'bg-emerald-50 text-emerald-600',
    },
    price_increase: { icon: ArrowUpRight, style: 'bg-amber-50 text-amber-600' },
    out_of_stock: { icon: PackageX, style: 'bg-rose-50 text-rose-600' },
    back_in_stock: { icon: PackageCheck, style: 'bg-blue-50 text-blue-600' },
    became_cheapest: {
      icon: BadgeCheck,
      style: 'bg-violet-50 text-violet-600',
    },
  }[type];
  const Icon = config.icon;
  return (
    <span
      className={`grid size-9 shrink-0 place-items-center rounded-xl ${config.style}`}
    >
      <Icon className="size-[18px]" />
    </span>
  );
}

export function EventFeed({
  events,
  compact = false,
}: {
  events: PriceChangeEvent[];
  compact?: boolean;
}) {
  if (!events.length)
    return (
      <p className="py-10 text-center text-sm text-slate-500">
        No recent price activity.
      </p>
    );
  return (
    <div className="divide-y divide-slate-100">
      {events.map((event) => (
        <Link
          key={event.id}
          href={`/products/${event.productId}`}
          className="flex gap-3.5 py-4 first:pt-1 last:pb-0 hover:[&_.event-title]:text-blue-600"
        >
          <EventIcon type={event.eventType} />
          <span className="min-w-0 flex-1">
            <span className="event-title block truncate text-sm font-medium text-slate-800 transition-colors">
              {event.productName}
            </span>
            <span
              className={`mt-0.5 block text-sm leading-5 text-slate-500 ${compact ? 'line-clamp-1' : ''}`}
            >
              {eventCopy(event)}
            </span>
          </span>
          <span className="shrink-0 pt-0.5 text-xs text-slate-400">
            {formatRelativeTime(event.timestamp)}
          </span>
        </Link>
      ))}
    </div>
  );
}
