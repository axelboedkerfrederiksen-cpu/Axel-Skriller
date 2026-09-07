import { buildProductComparison } from '@/lib/calculations';
import type {
  Competitor,
  CompetitorOffer,
  CustomerProduct,
  PriceChangeEvent,
  PriceHistoryPoint,
} from '@/lib/types';

const hoursAgo = (referenceTime: number, hours: number) =>
  new Date(referenceTime - hours * 60 * 60 * 1000).toISOString();

export const competitors: Competitor[] = [
  { id: 'northcart', name: 'NorthCart' },
  { id: 'marketlane', name: 'MarketLane' },
  { id: 'urbanbuy', name: 'UrbanBuy' },
  { id: 'shopnova', name: 'ShopNova' },
];

const productSeeds = [
  ['p-1001', 'Wireless Noise-Cancelling Headphones', 'AUD-1001', 1899],
  ['p-1002', 'Portable Bluetooth Speaker', 'AUD-1002', 749],
  ['p-1003', 'Smart Fitness Watch Pro', 'WEA-2001', 2199],
  ['p-1004', 'Mechanical Keyboard TKL', 'ACC-3012', 999],
  ['p-1005', 'Ergonomic Wireless Mouse', 'ACC-3018', 599],
  ['p-1006', '27” 4K USB-C Monitor', 'MON-4002', 3499],
  ['p-1007', 'USB-C Docking Station 12-in-1', 'ACC-3041', 1299],
  ['p-1008', '1080p Streaming Webcam', 'CAM-5004', 849],
  ['p-1009', 'Compact Mechanical Numpad', 'ACC-3055', 449],
  ['p-1010', 'Adjustable Laptop Stand', 'OFF-6003', 529],
  ['p-1011', 'GaN Charger 100W', 'POW-7001', 699],
  ['p-1012', 'Braided USB-C Cable 2m', 'CAB-8004', 189],
  ['p-1013', 'Smart LED Desk Lamp', 'OFF-6011', 629],
  ['p-1014', 'Portable SSD 2TB', 'STO-9002', 1399],
  ['p-1015', 'Wi-Fi 6 Mesh Router 2-pack', 'NET-9102', 1799],
  ['p-1016', '4K Action Camera', 'CAM-5022', 2399],
  ['p-1017', 'Multiroom Smart Speaker', 'AUD-1040', 1599],
  ['p-1018', 'E-reader 7” Paper Display', 'MOB-1107', 1499],
  ['p-1019', 'Universal Travel Adapter', 'POW-7022', 329],
  ['p-1020', 'Magnetic Power Bank 10K', 'POW-7031', 549],
  ['p-1021', 'Mini Projector Full HD', 'VID-1204', 2799],
  ['p-1022', 'Gaming Headset Wireless', 'AUD-1062', 1199],
  ['p-1023', 'Indoor Security Camera', 'CAM-5051', 679],
  ['p-1024', 'Air Quality Monitor', 'HOM-1301', 899],
] as const;

function createProducts(referenceTime: number): CustomerProduct[] {
  return productSeeds.map(([id, name, sku, price], index) => ({
    id,
    name,
    sku,
    customerPrice: price,
    currency: 'DKK',
    inStock: index !== 18,
    lastChecked: hoursAgo(
      referenceTime,
      index === 20 ? 11 : (index % 4) * 0.18 + 0.08,
    ),
  }));
}

const priceOffsets = [-0.08, -0.035, 0.025, 0.065];

function createOffers(
  products: CustomerProduct[],
  referenceTime: number,
): CompetitorOffer[] {
  return products.flatMap((product, productIndex) =>
    competitors.map((competitor, competitorIndex) => {
      const directionalShift =
        (((productIndex + competitorIndex * 2) % 7) - 3) * 0.012;
      const customerAdvantage = productIndex % 6 === 4 ? 0.12 : 0;
      const price =
        Math.round(
          (product.customerPrice! *
            (1 +
              priceOffsets[competitorIndex] +
              directionalShift +
              customerAdvantage)) /
            10,
        ) * 10;
      const failed = productIndex === 7 && competitorIndex === 2;
      const stale =
        (productIndex === 14 && competitorIndex === 1) ||
        (productIndex === 20 && competitorIndex < 2);
      const checkedHours = failed
        ? 18
        : stale
          ? 9 + competitorIndex
          : 0.08 + ((productIndex + competitorIndex) % 8) * 0.12;
      return {
        id: `${product.id}-${competitor.id}`,
        productId: product.id,
        competitorId: competitor.id,
        competitorName: competitor.name,
        price,
        currency: 'DKK' as const,
        inStock: (productIndex + competitorIndex * 3) % 13 !== 0,
        productUrl: `https://example.com/${competitor.id}/products/${product.id}`,
        lastChecked: hoursAgo(referenceTime, checkedHours),
        status: failed ? 'failed' : stale ? 'stale' : 'healthy',
      };
    }),
  );
}

const eventSeed: Omit<
  PriceChangeEvent,
  'id' | 'productName' | 'timestamp' | 'currency'
>[] = [
  {
    productId: 'p-1001',
    competitorId: 'northcart',
    competitorName: 'NorthCart',
    oldPrice: 1799,
    newPrice: 1699,
    percentageChange: -5.6,
    eventType: 'price_drop',
  },
  {
    productId: 'p-1006',
    competitorId: 'marketlane',
    competitorName: 'MarketLane',
    oldPrice: 3299,
    newPrice: 3099,
    percentageChange: -6.1,
    eventType: 'price_drop',
  },
  {
    productId: 'p-1014',
    competitorId: 'urbanbuy',
    competitorName: 'UrbanBuy',
    oldPrice: 1349,
    newPrice: 1399,
    percentageChange: 3.7,
    eventType: 'price_increase',
  },
  {
    productId: 'p-1003',
    competitorId: 'shopnova',
    competitorName: 'ShopNova',
    oldPrice: 2099,
    newPrice: 1999,
    percentageChange: -4.8,
    eventType: 'price_drop',
  },
  {
    productId: 'p-1008',
    competitorId: 'urbanbuy',
    competitorName: 'UrbanBuy',
    eventType: 'out_of_stock',
  },
  {
    productId: 'p-1011',
    oldPrice: 749,
    newPrice: 699,
    percentageChange: -6.7,
    eventType: 'became_cheapest',
  },
  {
    productId: 'p-1017',
    competitorId: 'marketlane',
    competitorName: 'MarketLane',
    oldPrice: 1499,
    newPrice: 1549,
    percentageChange: 3.3,
    eventType: 'price_increase',
  },
  {
    productId: 'p-1022',
    competitorId: 'northcart',
    competitorName: 'NorthCart',
    eventType: 'back_in_stock',
  },
];

function createEvents(
  products: CustomerProduct[],
  referenceTime: number,
): PriceChangeEvent[] {
  return eventSeed.map((event, index) => ({
    ...event,
    id: `evt-${index + 1}`,
    currency: 'DKK',
    productName:
      products.find((product) => product.id === event.productId)?.name ??
      'Product',
    timestamp: hoursAgo(
      referenceTime,
      [0.35, 1.2, 2.5, 4.2, 7.4, 11, 19, 31][index],
    ),
  }));
}

export function getMockDataset(referenceTime = Date.now()) {
  const products = createProducts(referenceTime);
  const offers = createOffers(products, referenceTime);
  const events = createEvents(products, referenceTime);
  const comparisons = products.map((product) =>
    buildProductComparison(
      product,
      offers.filter((offer) => offer.productId === product.id),
      events,
      referenceTime,
    ),
  );
  return { products, offers, events, comparisons };
}

export function getMockHistory(
  productId: string,
  referenceTime = Date.now(),
): PriceHistoryPoint[] {
  const { products, offers } = getMockDataset(referenceTime);
  const product = products.find((item) => item.id === productId);
  if (!product) return [];
  const productOffers = offers.filter((offer) => offer.productId === productId);
  const points: PriceHistoryPoint[] = [];
  for (let day = 20; day >= 0; day -= 2) {
    const timestamp = hoursAgo(referenceTime, day * 24);
    const customerWave = day > 8 ? 1.035 : day > 2 ? 1.015 : 1;
    points.push({
      timestamp,
      price: Math.round(product.customerPrice! * customerWave),
      sourceType: 'customer',
    });
    productOffers.forEach((offer, competitorIndex) => {
      const phase = Math.sin((day + competitorIndex * 2) / 3) * 0.018;
      const earlierPremium = day > 10 && competitorIndex < 2 ? 0.035 : 0;
      points.push({
        timestamp,
        price: Math.round(offer.price! * (1 + phase + earlierPremium)),
        sourceType: 'competitor',
        competitorId: offer.competitorId,
        competitorName: offer.competitorName,
      });
    });
  }
  return points;
}
