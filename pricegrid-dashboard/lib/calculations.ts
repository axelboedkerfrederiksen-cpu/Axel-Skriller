import type {
  CompetitorOffer,
  CustomerProduct,
  MonitorStatus,
  PriceChangeEvent,
  ProductComparison,
} from '@/lib/types';

const HOUR = 60 * 60 * 1000;

export function getCheapestOffer(offers: CompetitorOffer[]) {
  return (
    offers
      .filter((offer) => offer.inStock === true && offer.price !== null)
      .sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity))[0] ?? null
  );
}

export function getCustomerRank(
  customerPrice: number | null,
  offers: CompetitorOffer[],
) {
  if (customerPrice === null) return null;
  return (
    1 +
    offers.filter(
      (offer) =>
        offer.inStock === true &&
        offer.price !== null &&
        offer.price < customerPrice,
    ).length
  );
}

export function getMonitorStatus(
  offers: CompetitorOffer[],
  referenceTime = Date.now(),
): MonitorStatus {
  if (offers.some((offer) => offer.status === 'failed')) return 'failed';
  if (
    offers.some(
      (offer) =>
        offer.status === 'stale' ||
        referenceTime - new Date(offer.lastChecked).getTime() > 6 * HOUR,
    )
  )
    return 'stale';
  return 'healthy';
}

export function buildProductComparison(
  product: CustomerProduct,
  offers: CompetitorOffer[],
  events: PriceChangeEvent[] = [],
  referenceTime = Date.now(),
): ProductComparison {
  const cheapestCompetitor = getCheapestOffer(offers);
  const cheapestPrice = cheapestCompetitor?.price ?? null;
  const differenceAmount =
    cheapestPrice === null || product.customerPrice === null
      ? null
      : product.customerPrice - cheapestPrice;
  const differencePercentage =
    differenceAmount === null || cheapestPrice === null || cheapestPrice === 0
      ? null
      : (differenceAmount / cheapestPrice) * 100;
  const recentWindow = referenceTime - 24 * HOUR;
  const recentEvents = events.filter(
    (event) =>
      event.productId === product.id &&
      new Date(event.timestamp).getTime() >= recentWindow,
  );
  return {
    product,
    competitorOffers: offers,
    cheapestCompetitor,
    cheapestPrice,
    customerPrice: product.customerPrice,
    differenceAmount,
    differencePercentage,
    customerRank: getCustomerRank(product.customerPrice, offers),
    isCustomerCheapest:
      differenceAmount === null ? null : differenceAmount <= 0,
    hasRecentCompetitorDrop: recentEvents.some(
      (event) => event.eventType === 'price_drop' && event.competitorId,
    ),
    hasRecentCompetitorIncrease: recentEvents.some(
      (event) => event.eventType === 'price_increase' && event.competitorId,
    ),
    status: getMonitorStatus(offers),
  };
}

export function formatCurrency(value: number | null, currency = 'DKK') {
  if (value === null) return '—';
  return new Intl.NumberFormat('da-DK', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatPercentage(value: number | null) {
  if (value === null) return '—';
  return `${value > 0 ? '+' : ''}${new Intl.NumberFormat('da-DK', { maximumFractionDigits: 1 }).format(value)}%`;
}

export function formatRelativeTime(timestamp: string | null) {
  if (!timestamp) return 'Not checked yet';
  const minutes = Math.max(
    0,
    Math.round((Date.now() - new Date(timestamp).getTime()) / 60000),
  );
  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
