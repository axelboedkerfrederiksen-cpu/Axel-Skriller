export type Currency = string;
export type MonitorStatus = 'healthy' | 'stale' | 'failed';

export interface CustomerProduct {
  id: string;
  name: string;
  sku: string;
  customerPrice: number | null;
  currency: Currency;
  imageUrl?: string | null;
  inStock: boolean | null;
  lastChecked: string;
}

export interface Competitor {
  id: string;
  name: string;
}

export interface CompetitorOffer {
  id: string;
  productId: string;
  competitorId: string;
  competitorName: string;
  price: number | null;
  currency: Currency;
  inStock: boolean | null;
  productUrl: string;
  lastChecked: string;
  status: MonitorStatus;
}

export interface PriceHistoryPoint {
  timestamp: string;
  price: number;
  sourceType: 'customer' | 'competitor';
  competitorId?: string | null;
  competitorName?: string | null;
}

export type PriceEventType =
  | 'price_drop'
  | 'price_increase'
  | 'out_of_stock'
  | 'back_in_stock'
  | 'became_cheapest';

export interface PriceChangeEvent {
  id: string;
  productId: string;
  productName: string;
  competitorId?: string | null;
  competitorName?: string | null;
  currency: Currency;
  oldPrice?: number | null;
  newPrice?: number | null;
  percentageChange?: number | null;
  timestamp: string;
  eventType: PriceEventType;
}

export interface ProductComparison {
  product: CustomerProduct;
  competitorOffers: CompetitorOffer[];
  cheapestCompetitor: CompetitorOffer | null;
  cheapestPrice: number | null;
  customerPrice: number | null;
  differenceAmount: number | null;
  differencePercentage: number | null;
  customerRank: number | null;
  isCustomerCheapest: boolean | null;
  hasRecentCompetitorDrop: boolean;
  hasRecentCompetitorIncrease: boolean;
  status: MonitorStatus;
}

export interface DashboardData {
  totalProducts: number;
  monitoredOffers: number;
  priceChanges24h: number;
  overpricedProducts: number;
  cheapestProducts: number;
  staleOrFailed: number;
  recentEvents: PriceChangeEvent[];
  largestGaps: ProductComparison[];
  freshness: {
    status: MonitorStatus;
    lastSuccessfulUpdate: string | null;
    healthyPercentage: number;
    checkedLastHour: number;
  };
}

export interface ProductDetailData {
  comparison: ProductComparison;
  history: PriceHistoryPoint[];
  events: PriceChangeEvent[];
}

export interface CompetitorSummary extends Competitor {
  monitoredProducts: number;
  averageDifferencePercentage: number | null;
  cheapestProducts: number;
  lastSuccessfulScrape: string | null;
  status: MonitorStatus;
  successRate: number;
}

export interface SiteMonitorStatus extends Competitor {
  healthyMonitors: number;
  staleMonitors: number;
  failedChecks: number;
  lastSuccessfulUpdate: string | null;
  status: MonitorStatus;
}

export interface HealthData {
  healthyMonitors: number;
  staleMonitors: number;
  failedChecks: number;
  totalMonitors: number;
  lastSuccessfulUpdate: string | null;
  sites: SiteMonitorStatus[];
}
