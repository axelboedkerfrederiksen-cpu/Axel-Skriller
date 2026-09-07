import {
  ApiError,
  apiGet,
  customerDashboardPath,
  isMockApiEnabled,
} from '@/lib/api/client';
import { getMockDataset, getMockHistory } from '@/lib/mock/data';
import type { ProductComparison, ProductDetailData } from '@/lib/types';

export async function getProducts(): Promise<ProductComparison[]> {
  if (!isMockApiEnabled)
    return apiGet<ProductComparison[]>(customerDashboardPath('/products'));
  return getMockDataset().comparisons;
}

export async function getProductDetail(
  id: string,
): Promise<ProductDetailData | null> {
  if (!isMockApiEnabled) {
    try {
      return await apiGet<ProductDetailData>(
        customerDashboardPath(`/products/${encodeURIComponent(id)}`),
      );
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
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
