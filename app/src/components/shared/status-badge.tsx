import { cn } from '@/lib/utils';

interface StatusBadgeProps {
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'CACHED' | 'FAILED' | 'PARTIAL';
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const configs = {
    PENDING: { label: 'Pending', color: 'bg-muted text-muted-foreground' },
    RUNNING: { label: 'Running', color: 'bg-primary/20 text-primary animate-pulse' },
    COMPLETED: { label: 'Completed', color: 'bg-green-500/10 text-green-500' },
    CACHED: { label: 'Cached', color: 'bg-blue-500/10 text-blue-500' },
    FAILED: { label: 'Failed', color: 'bg-destructive/10 text-destructive' },
    PARTIAL: { label: 'Partial', color: 'bg-yellow-500/10 text-yellow-500' },
  };

  const config = configs[status];

  return (
    <div className={cn(
      "px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-tighter flex items-center gap-1 w-fit",
      config.color,
      className
    )}>
      {status === 'RUNNING' && <div className="w-1 h-1 bg-primary rounded-full animate-ping" />}
      {status === 'CACHED' && <span className="text-[10px]">🕒</span>}
      {config.label}
    </div>
  );
}
