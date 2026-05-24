import { Skeleton } from '@/components/ui/skeleton';

export function PaperCardSkeleton() {
  return (
    <div className="bg-[#0f0f0f] border border-[#1a1a1a] rounded-xl p-5 space-y-4">
      <div className="flex justify-between">
        <div className="flex gap-2">
          <Skeleton className="h-5 w-12 bg-secondary" />
          <Skeleton className="h-5 w-16 bg-secondary" />
        </div>
        <Skeleton className="h-5 w-16 bg-secondary rounded-full" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-6 w-3/4 bg-secondary" />
        <Skeleton className="h-4 w-1/2 bg-secondary" />
      </div>
      <div className="flex gap-2 pt-2">
        <Skeleton className="h-8 w-8 bg-secondary rounded-md" />
        <Skeleton className="h-8 w-8 bg-secondary rounded-md" />
        <Skeleton className="h-8 w-8 bg-secondary rounded-md" />
      </div>
      <Skeleton className="h-10 w-full bg-secondary rounded-md mt-4" />
    </div>
  );
}

export function PaperViewerSkeleton() {
  return (
    <div className="flex flex-col h-screen">
      <div className="h-24 border-b border-[#1a1a1a] p-8 flex justify-between items-center">
        <div className="space-y-2">
          <Skeleton className="h-8 w-64 bg-secondary" />
          <Skeleton className="h-4 w-48 bg-secondary" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-8 w-24 bg-secondary" />
          <Skeleton className="h-8 w-24 bg-secondary" />
        </div>
      </div>
      <div className="flex-1 p-8 flex gap-8">
        <div className="flex-[0.65] space-y-8">
          <Skeleton className="h-12 w-full bg-secondary" />
          <Skeleton className="h-[400px] w-full bg-secondary rounded-xl" />
        </div>
        <div className="flex-[0.35] space-y-6">
          <Skeleton className="h-6 w-32 bg-secondary" />
          <div className="space-y-4">
            {[1, 2, 3, 4, 5].map(i => (
              <Skeleton key={i} className="h-12 w-full bg-secondary" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
