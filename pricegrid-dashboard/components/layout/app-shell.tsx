'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  BarChart3,
  Boxes,
  ChevronDown,
  Menu,
  Radio,
  Store,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

const navigation = [
  { href: '/', label: 'Overview', icon: BarChart3 },
  { href: '/products', label: 'Products', icon: Boxes },
  { href: '/competitors', label: 'Competitors', icon: Store },
  { href: '/monitoring', label: 'Monitoring', icon: Activity },
];

function Brand() {
  return (
    <Link
      href="/"
      className="flex items-center gap-3"
      aria-label="Pricegrid overview"
    >
      <span className="grid size-9 place-items-center rounded-xl bg-blue-500 text-white shadow-[0_8px_24px_rgb(59_130_246/25%)]">
        <span className="flex h-4 items-end gap-0.5" aria-hidden="true">
          <i className="h-2 w-1 rounded-full bg-white/70" />
          <i className="h-4 w-1 rounded-full bg-white" />
          <i className="h-3 w-1 rounded-full bg-white/85" />
        </span>
      </span>
      <span className="text-[1.05rem] font-semibold tracking-[-0.03em] text-white">
        Pricegrid
      </span>
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="space-y-1" aria-label="Primary navigation">
      {navigation.map((item) => {
        const Icon = item.icon;
        const active =
          item.href === '/' ? pathname === '/' : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              'group flex h-11 items-center gap-3 rounded-xl px-3 text-[0.9rem] font-medium transition-colors',
              active
                ? 'bg-white/10 text-white shadow-[inset_0_0_0_1px_rgb(255_255_255/7%)]'
                : 'text-slate-400 hover:bg-white/5 hover:text-slate-100',
            )}
          >
            <Icon className={cn('size-[18px]', active && 'text-blue-400')} />
            {item.label}
            {active && (
              <span className="ml-auto size-1.5 rounded-full bg-blue-400" />
            )}
          </Link>
        );
      })}
    </nav>
  );
}

export function AppShell({
  children,
  isMockData,
}: {
  children: React.ReactNode;
  isMockData: boolean;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  return (
    <div className="min-h-screen bg-[#f5f7fb]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 flex-col bg-[#111827] px-4 py-5 md:flex">
        <div className="px-2">
          <Brand />
        </div>
        <div className="mt-9">
          <NavLinks />
        </div>
        <div className="mt-auto rounded-2xl border border-white/10 bg-white/[0.055] p-3.5">
          <div className="flex items-center gap-2 text-[0.8rem] font-medium text-slate-200">
            <span className="relative flex size-2.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50" />
              <span className="relative inline-flex size-2.5 rounded-full bg-emerald-400" />
            </span>
            {isMockData ? 'Demo monitoring' : 'Price Monitor connected'}
          </div>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            {isMockData
              ? 'Explore the dashboard with sample prices'
              : 'Live pricing data from the monitoring backend'}
          </p>
        </div>
        <button
          className="mt-3 flex items-center gap-3 rounded-xl px-2 py-2 text-left text-sm text-slate-300 hover:bg-white/5"
          type="button"
        >
          <span className="grid size-8 place-items-center rounded-lg bg-blue-500/20 font-semibold text-blue-300">
            DW
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-slate-200">
              Pricegrid workspace
            </span>
            <span className="block text-xs text-slate-500">
              {isMockData ? 'Demo account' : 'Connected account'}
            </span>
          </span>
          <ChevronDown className="size-4 text-slate-500" />
        </button>
      </aside>
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur-xl md:ml-64 md:px-7">
        <div className="flex items-center gap-3 md:hidden">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            className="grid size-10 place-items-center rounded-xl border border-slate-200 text-slate-600"
            aria-label="Open navigation"
          >
            <Menu className="size-5" />
          </button>
          <span className="font-semibold tracking-tight text-slate-900">
            Pricegrid
          </span>
        </div>
        <div className="hidden items-center gap-2 text-sm text-slate-500 md:flex">
          <Radio className="size-4 text-emerald-500" />
          {isMockData ? 'Demo monitoring' : 'Live monitoring connected'}
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 sm:inline-flex">
            {isMockData ? 'Demo data' : 'Live data'}
          </span>
          <button
            type="button"
            className="grid size-9 place-items-center rounded-full bg-slate-900 text-xs font-semibold text-white"
          >
            AK
          </button>
        </div>
      </header>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            className="absolute inset-0 bg-slate-950/50"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation overlay"
          />
          <aside className="relative flex h-full w-[min(82vw,300px)] flex-col bg-[#111827] p-5 shadow-2xl">
            <div className="flex items-center justify-between">
              <Brand />
              <button
                type="button"
                className="grid size-9 place-items-center rounded-lg text-slate-400 hover:bg-white/10"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation"
              >
                <X className="size-5" />
              </button>
            </div>
            <div className="mt-9">
              <NavLinks onNavigate={() => setMobileOpen(false)} />
            </div>
          </aside>
        </div>
      )}
      <main className="md:ml-64">
        <div className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
