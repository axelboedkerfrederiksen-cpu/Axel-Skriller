import {
  apiGet,
  customerDashboardPath,
  isMockApiEnabled,
} from '@/lib/api/client';
import { getMockDataset } from '@/lib/mock/data';
import type { DashboardData } from '@/lib/types';

export async function getDashboardData(): Promise<DashboardData> {
  if (!isMockApiEnabled) return apiGet<DashboardData>(customerDashboardPath());
  const { comparisons, events, offers } = getMockDataset();
  const recentEvents = events.filter(
    (event) =>
      Date.now() - new Date(event.timestamp).getTime() <= 24 * 60 * 60 * 1000,
  );
  const healthyOffers = offers.filter((offer) => offer.status === 'healthy');
  const successfulOffers = offers.filter((offer) => offer.status !== 'failed');
  return {
    totalProducts: comparisons.length,
    monitoredOffers: offers.length,
    priceChanges24h: recentEvents.filter((event) =>
      ['price_drop', 'price_increase'].includes(event.eventType),
    ).length,
    overpricedProducts: comparisons.filter(
      (item) => (item.differenceAmount ?? 0) > 0,
    ).length,
    cheapestProducts: comparisons.filter((item) => item.isCustomerCheapest)
      .length,
    staleOrFailed: offers.filter((offer) => offer.status !== 'healthy').length,
    recentEvents: recentEvents.slice(0, 6),
    largestGaps: [...comparisons]
      .filter((item) => (item.differenceAmount ?? 0) > 0)
      .sort((a, b) => (b.differenceAmount ?? 0) - (a.differenceAmount ?? 0))
      .slice(0, 5),
    freshness: {
      status:
        offers.length && healthyOffers.length / offers.length > 0.95
          ? 'healthy'
          : 'stale',
      lastSuccessfulUpdate:
        successfulOffers
          .map((offer) => offer.lastChecked)
          .sort()
          .at(-1) ?? null,
      healthyPercentage: offers.length
        ? Math.round((healthyOffers.length / offers.length) * 100)
        : 0,
      checkedLastHour: offers.filter(
        (offer) =>
          Date.now() - new Date(offer.lastChecked).getTime() < 60 * 60 * 1000,
      ).length,
    },
  };
}
