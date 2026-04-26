import { LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({ icon: Icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center space-y-4 animate-in fade-in duration-500">
      <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center text-muted-foreground">
        <Icon className="w-8 h-8" />
      </div>
      <div className="space-y-1">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground max-w-xs mx-auto">
          {description}
        </p>
      </div>
      {actionLabel && onAction && (
        <Button className="bg-primary" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
