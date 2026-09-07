export type Currency = 'DKK';
export type MonitorStatus = 'healthy' | 'stale' | 'failed';

export interface CustomerProduct {
  id: string;
  name: string;
  sku: string;
  customerPrice: number;
  currency: Currency;
  imageUrl?: string;
  inStock: boolean;
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
  price: number;
  currency: Currency;
  inStock: boolean;
  productUrl: string;
  lastChecked: string;
  status: MonitorStatus;
}

export interface PriceHistoryPoint {
  timestamp: string;
  price: number;
  sourceType: 'customer' | 'competitor';
  competitorId?: string;
  competitorName?: string;
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
  competitorId?: string;
  competitorName?: string;
  oldPrice?: number;
  newPrice?: number;
  percentageChange?: number;
  timestamp: string;
  eventType: PriceEventType;
}

export interface ProductComparison {
  product: CustomerProduct;
  competitorOffers: CompetitorOffer[];
  cheapestCompetitor: CompetitorOffer | null;
  cheapestPrice: number | null;
  customerPrice: number;
  differenceAmount: number | null;
  differencePercentage: number | null;
  customerRank: number;
  isCustomerCheapest: boolean;
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
    lastSuccessfulUpdate: string;
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
  averageDifferencePercentage: number;
  cheapestProducts: number;
  lastSuccessfulScrape: string;
  status: MonitorStatus;
  successRate: number;
}

export interface SiteMonitorStatus extends Competitor {
  healthyMonitors: number;
  staleMonitors: number;
  failedChecks: number;
  lastSuccessfulUpdate: string;
  status: MonitorStatus;
}

export interface HealthData {
  healthyMonitors: number;
  staleMonitors: number;
  failedChecks: number;
  totalMonitors: number;
  lastSuccessfulUpdate: string;
  sites: SiteMonitorStatus[];
}
