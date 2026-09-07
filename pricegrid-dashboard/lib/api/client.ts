const baseUrl = process.env.PRICE_MONITOR_API_BASE_URL?.replace(/\/$/, '');
const apiToken = process.env.PRICE_MONITOR_API_TOKEN;
const customerId = process.env.PRICE_MONITOR_CUSTOMER_ID;

export const isMockApiEnabled =
  process.env.PRICEGRID_USE_MOCK_API !== 'false' || !baseUrl || !customerId;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function customerDashboardPath(path = '') {
  if (!customerId)
    throw new Error('PRICE_MONITOR_CUSTOMER_ID is not configured.');
  return `/api/v1/customers/${encodeURIComponent(customerId)}/dashboard${path}`;
}

export async function apiGet<T>(path: string): Promise<T> {
  if (!baseUrl)
    throw new Error('PRICE_MONITOR_API_BASE_URL is not configured.');
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (apiToken) headers.Authorization = `Bearer ${apiToken}`;
  const response = await fetch(`${baseUrl}${path}`, {
    headers,
    cache: 'no-store',
  });
  if (!response.ok)
    throw new ApiError(
      `Price Monitor returned ${response.status}.`,
      response.status,
    );
  return response.json() as Promise<T>;
}
