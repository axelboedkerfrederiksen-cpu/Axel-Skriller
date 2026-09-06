const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, '');
export const useMockApi =
  process.env.NEXT_PUBLIC_USE_MOCK_API !== 'false' || !baseUrl;

export async function apiGet<T>(path: string): Promise<T> {
  if (!baseUrl) throw new Error('NEXT_PUBLIC_API_BASE_URL is not configured.');
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { Accept: 'application/json' },
    next: { revalidate: 60 },
  });
  if (!response.ok)
    throw new Error(`API request failed with ${response.status}.`);
  return response.json() as Promise<T>;
}
