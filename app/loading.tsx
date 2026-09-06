import { Skeleton } from '@/components/ui/skeleton';

export default function Loading() {
  return (
    <div aria-label="Loading dashboard">
      <div className="space-y-2">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="mt-7 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-36 rounded-2xl" />
        ))}
      </div>
      <Skeleton className="mt-6 h-[420px] rounded-2xl" />
    </div>
  );
}
