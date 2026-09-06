import { apiGet, useMockApi } from '@/lib/api/client';
import { competitors, offers } from '@/lib/mock/data';
import type { HealthData } from '@/lib/types';

export async function getHealth(): Promise<HealthData> {
  if (!useMockApi) return apiGet<HealthData>('/api/health');
  const healthyMonitors = offers.filter(
    (offer) => offer.status === 'healthy',
  ).length;
  const staleMonitors = offers.filter(
    (offer) => offer.status === 'stale',
  ).length;
  const failedChecks = offers.filter(
    (offer) => offer.status === 'failed',
  ).length;
  const successful = offers.filter((offer) => offer.status !== 'failed');
  return {
    healthyMonitors,
    staleMonitors,
    failedChecks,
    totalMonitors: offers.length,
    lastSuccessfulUpdate: successful
      .map((offer) => offer.lastChecked)
      .sort()
      .at(-1)!,
    sites: competitors.map((competitor) => {
      const siteOffers = offers.filter(
        (offer) => offer.competitorId === competitor.id,
      );
      const healthy = siteOffers.filter(
        (offer) => offer.status === 'healthy',
      ).length;
      const stale = siteOffers.filter(
        (offer) => offer.status === 'stale',
      ).length;
      const failed = siteOffers.filter(
        (offer) => offer.status === 'failed',
      ).length;
      return {
        ...competitor,
        healthyMonitors: healthy,
        staleMonitors: stale,
        failedChecks: failed,
        lastSuccessfulUpdate: siteOffers
          .filter((offer) => offer.status !== 'failed')
          .map((offer) => offer.lastChecked)
          .sort()
          .at(-1)!,
        status: failed ? 'failed' : stale ? 'stale' : 'healthy',
      };
    }),
  };
}
