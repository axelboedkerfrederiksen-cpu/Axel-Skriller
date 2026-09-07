import { apiGet, useMockApi } from '@/lib/api/client';
import { getMockDataset, getMockHistory } from '@/lib/mock/data';
import type {
  PriceChangeEvent,
  PriceHistoryPoint,
  ProductComparison,
  ProductDetailData,
} from '@/lib/types';

interface ProductDetailResponse {
  comparison: ProductComparison;
  events: PriceChangeEvent[];
}

export async function getProducts(): Promise<ProductComparison[]> {
  if (!useMockApi) return apiGet<ProductComparison[]>('/api/products');
  return getMockDataset().comparisons;
}

export async function getProductDetail(
  id: string,
): Promise<ProductDetailData | null> {
  if (!useMockApi) {
    const [detail, history] = await Promise.all([
      apiGet<ProductDetailResponse>(`/api/products/${encodeURIComponent(id)}`),
      apiGet<PriceHistoryPoint[]>(
        `/api/products/${encodeURIComponent(id)}/history`,
      ),
    ]);
    return { ...detail, history };
  }
  const referenceTime = Date.now();
  const { comparisons, events } = getMockDataset(referenceTime);
  const comparison = comparisons.find((item) => item.product.id === id);
  if (!comparison) return null;
  return {
    comparison,
    history: getMockHistory(id, referenceTime),
    events: events.filter((event) => event.productId === id),
  };
}
