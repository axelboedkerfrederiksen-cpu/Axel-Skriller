import { apiGet, useMockApi } from '@/lib/api/client';
import { comparisons, competitors, offers, products } from '@/lib/mock/data';
import type { CompetitorSummary } from '@/lib/types';

export async function getCompetitors(): Promise<CompetitorSummary[]> {
  if (!useMockApi) return apiGet<CompetitorSummary[]>('/api/competitors');
  return competitors.map((competitor) => {
    const competitorOffers = offers.filter(
      (offer) => offer.competitorId === competitor.id,
    );
    const validOffers = competitorOffers.filter(
      (offer) => offer.status !== 'failed',
    );
    const differences = validOffers.map((offer) => {
      const product = products.find((item) => item.id === offer.productId)!;
      return (
        ((offer.price - product.customerPrice) / product.customerPrice) * 100
      );
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
      averageDifferencePercentage:
        differences.reduce((sum, value) => sum + value, 0) / differences.length,
      cheapestProducts: comparisons.filter(
        (item) => item.cheapestCompetitor?.competitorId === competitor.id,
      ).length,
      lastSuccessfulScrape: validOffers
        .map((offer) => offer.lastChecked)
        .sort()
        .at(-1)!,
      status: failed > 0 ? 'failed' : stale > 0 ? 'stale' : 'healthy',
      successRate: Math.round(
        (validOffers.length / competitorOffers.length) * 100,
      ),
    };
  });
}
