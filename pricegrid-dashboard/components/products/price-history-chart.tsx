'use client';

import { useMemo, useState } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatCurrency } from '@/lib/calculations';
import type { PriceHistoryPoint } from '@/lib/types';
import { cn } from '@/lib/utils';

const colors = ['#2563eb', '#10b981', '#f59e0b', '#8b5cf6', '#06b6d4'];

export function PriceHistoryChart({
  history,
}: {
  history: PriceHistoryPoint[];
}) {
  const { chartData, series } = useMemo(() => {
    const seriesList = [
      { key: 'customer', label: 'Your store', color: colors[0] },
      ...Array.from(
        new Map(
          history
            .filter((point) => point.competitorId)
            .map((point) => [point.competitorId!, point.competitorName!]),
        ).entries(),
      ).map(([id, name], index) => ({
        key: id,
        label: name,
        color: colors[index + 1],
      })),
    ];
    const grouped = new Map<string, Record<string, string | number>>();
    history.forEach((point) => {
      const row = grouped.get(point.timestamp) ?? {
        timestamp: point.timestamp,
      };
      row[point.sourceType === 'customer' ? 'customer' : point.competitorId!] =
        point.price;
      grouped.set(point.timestamp, row);
    });
    return {
      chartData: [...grouped.values()].sort((a, b) =>
        String(a.timestamp).localeCompare(String(b.timestamp)),
      ),
      series: seriesList,
    };
  }, [history]);
  const [visible, setVisible] = useState<string[]>(
    series.map((item) => item.key),
  );

  function toggleSeries(key: string) {
    setVisible((current) =>
      current.includes(key)
        ? current.filter((item) => item !== key)
        : [...current, key],
    );
  }

  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-2">
        {series.map((item) => {
          const active = visible.includes(item.key);
          return (
            <button
              key={item.key}
              type="button"
              aria-pressed={active}
              onClick={() => toggleSeries(item.key)}
              className={cn(
                'inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors',
                active
                  ? 'border-slate-200 bg-white text-slate-700 shadow-sm'
                  : 'border-transparent bg-slate-100 text-slate-400',
              )}
            >
              <span
                className="size-2 rounded-full"
                style={{ backgroundColor: active ? item.color : '#cbd5e1' }}
              />
              {item.label}
            </button>
          );
        })}
      </div>
      <div className="h-[320px] w-full sm:h-[360px]">
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          minHeight={0}
          initialDimension={{ width: 960, height: 360 }}
        >
          <LineChart
            data={chartData}
            margin={{ top: 8, right: 10, left: 0, bottom: 0 }}
          >
            <CartesianGrid
              vertical={false}
              stroke="#e8edf4"
              strokeDasharray="3 3"
            />
            <XAxis
              dataKey="timestamp"
              tickFormatter={(value) =>
                new Intl.DateTimeFormat('en-DK', {
                  day: 'numeric',
                  month: 'short',
                }).format(new Date(value))
              }
              tick={{ fontSize: 12, fill: '#94a3b8' }}
              tickLine={false}
              axisLine={false}
              minTickGap={28}
              dy={8}
            />
            <YAxis
              tickFormatter={(value) =>
                `${Math.round(Number(value) / 100) * 100}`
              }
              tick={{ fontSize: 12, fill: '#94a3b8' }}
              tickLine={false}
              axisLine={false}
              width={50}
              domain={['auto', 'auto']}
            />
            <Tooltip
              cursor={{ stroke: '#cbd5e1', strokeDasharray: '3 3' }}
              contentStyle={{
                borderRadius: 12,
                borderColor: '#e2e8f0',
                boxShadow: '0 12px 28px rgb(15 23 42 / 10%)',
                fontSize: 13,
              }}
              labelFormatter={(value) =>
                new Intl.DateTimeFormat('en-DK', {
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                }).format(new Date(String(value)))
              }
              formatter={(value) => formatCurrency(Number(value))}
            />
            <Legend wrapperStyle={{ display: 'none' }} />
            {series.map(
              (item) =>
                visible.includes(item.key) && (
                  <Line
                    key={item.key}
                    type="monotone"
                    dataKey={item.key}
                    name={item.label}
                    stroke={item.color}
                    strokeWidth={item.key === 'customer' ? 3 : 2}
                    dot={false}
                activeDot={{ r: 4, strokeWidth: 2, fill: '#fff' }}
                connectNulls
                isAnimationActive={false}
              />
                ),
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
