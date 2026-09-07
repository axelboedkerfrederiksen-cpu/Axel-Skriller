import {
  apiGet,
  customerDashboardPath,
  isMockApiEnabled,
} from '@/lib/api/client';
import { competitors, getMockDataset } from '@/lib/mock/data';
import type { CompetitorSummary } from '@/lib/types';

export async function getCompetitors(): Promise<CompetitorSummary[]> {
  if (!isMockApiEnabled)
    return apiGet<CompetitorSummary[]>(customerDashboardPath('/competitors'));
  const { comparisons, offers, products } = getMockDataset();
  return competitors.map((competitor) => {
    const competitorOffers = offers.filter(
      (offer) => offer.competitorId === competitor.id,
    );
    const validOffers = competitorOffers.filter(
      (offer) => offer.status !== 'failed',
    );
    const differences = validOffers.flatMap((offer) => {
      const product = products.find((item) => item.id === offer.productId)!;
      if (offer.price === null || product.customerPrice === null) return [];
      return [
        ((offer.price - product.customerPrice) / product.customerPrice) * 100,
      ];
    });
    const failed = competitorOffers.filter(
      (offer) => offer.status === 'failed',
    ).length;
    const stale = competitorOffers.filter(
      (offer) => offer.status === 'stale',
    ).length;
    return {
      ...competitor,
      monitoredProducts: competitorOffers.length,
      averageDifferencePercentage: differences.length
        ? differences.reduce((sum, value) => sum + value, 0) /
          differences.length
        : null,
      cheapestProducts: comparisons.filter(
        (item) => item.cheapestCompetitor?.competitorId === competitor.id,
      ).length,
      lastSuccessfulScrape:
        validOffers
          .map((offer) => offer.lastChecked)
          .sort()
          .at(-1) ?? null,
      status:
        failed > 0
          ? 'failed'
          : stale > 0 || competitorOffers.length === 0
            ? 'stale'
            : 'healthy',
      successRate: competitorOffers.length
        ? Math.round((validOffers.length / competitorOffers.length) * 100)
        : 0,
    };
  });
}
