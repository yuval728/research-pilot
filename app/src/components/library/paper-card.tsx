import { Link } from 'react-router-dom';
import { ChevronRight, Code2, FileText, GitBranch } from 'lucide-react';
import { Paper, PipelineRun } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { toDisplayStatus } from '@/lib/pipeline-status';
import { cn } from '@/lib/utils';

interface PaperCardProps {
  paper: Paper;
  pipelineRun?: PipelineRun | null;
}

type DisplayStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export function PaperCard({ paper, pipelineRun }: PaperCardProps) {
  const status = toDisplayStatus(pipelineRun);
  const meta = paper.metadata;

  return (
    <Card className="bg-[#0f0f0f] border-[#1a1a1a] hover:border-primary/50 transition-all group overflow-hidden">
      <CardHeader className="p-5 pb-3">
        <div className="flex items-center justify-between mb-3">
          <div className="flex gap-2 flex-wrap">
            {meta?.domain && (
              <Badge
                variant="secondary"
                className="bg-secondary/50 text-muted-foreground text-[10px] font-bold uppercase tracking-wider border-none"
              >
                {meta.domain}
              </Badge>
            )}
            {meta?.sub_domain && (
              <Badge
                variant="secondary"
                className="bg-primary/10 text-primary text-[10px] font-bold uppercase tracking-wider border-none"
              >
                {meta.sub_domain}
              </Badge>
            )}
          </div>
          <StatusBadge status={status} />
        </div>
        <h3 className="text-base font-semibold leading-tight line-clamp-2 group-hover:text-primary transition-colors">
          {meta?.title ?? 'Untitled Paper'}
        </h3>
        {meta?.authors && meta.authors.length > 0 && (
          <p className="text-sm text-muted-foreground truncate mt-1">
            {meta.authors.join(', ')}
          </p>
        )}
        {(meta?.venue || meta?.year) && (
          <div className="flex items-center gap-2 mt-2 text-[10px] text-muted-foreground font-medium uppercase tracking-widest">
            {meta.venue && <span>{meta.venue}</span>}
            {meta.venue && meta.year && <span>•</span>}
            {meta.year && <span>{meta.year}</span>}
          </div>
        )}
      </CardHeader>

      <CardContent className="p-5 pt-0">
        {status === 'RUNNING' ? (
          <div className="flex items-center gap-3 py-2">
            <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary animate-progress-indeterminate" />
            </div>
            <span className="text-[10px] font-bold text-primary animate-pulse">PROCESSING</span>
          </div>
        ) : status === 'FAILED' ? (
          <div className="bg-destructive/10 text-destructive text-[10px] font-bold p-2 rounded border border-destructive/20">
            PIPELINE FAILED
          </div>
        ) : status === 'PENDING' ? (
          <div className="bg-muted/30 text-muted-foreground text-[10px] font-bold p-2 rounded border border-muted/20">
            AWAITING PIPELINE
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10"
              title="View diagrams"
            >
              <GitBranch className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10"
              title="View code"
            >
              <Code2 className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10"
              title="View report"
            >
              <FileText className="w-4 h-4" />
            </Button>
          </div>
        )}
      </CardContent>

      <CardFooter className="p-0 border-t border-[#1a1a1a]">
        <Link
          to={`/papers/${paper.id}`}
          className="w-full flex items-center justify-between px-5 py-3 text-xs font-bold uppercase tracking-widest hover:bg-secondary transition-colors"
        >
          View Analysis
          <ChevronRight className="w-4 h-4" />
        </Link>
      </CardFooter>
    </Card>
  );
}

function StatusBadge({ status }: { status: DisplayStatus }) {
  const configs: Record<DisplayStatus, { label: string; color: string }> = {
    PENDING: { label: 'Pending', color: 'bg-muted text-muted-foreground' },
    RUNNING: { label: 'Running', color: 'bg-primary/20 text-primary' },
    COMPLETED: { label: 'Completed', color: 'bg-green-500/10 text-green-500' },
    FAILED: { label: 'Failed', color: 'bg-destructive/10 text-destructive' },
  };

  const config = configs[status];

  return (
    <div
      className={cn(
        'px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-tighter flex items-center gap-1',
        config.color,
      )}
    >
      {status === 'RUNNING' && <div className="w-1 h-1 bg-primary rounded-full animate-ping" />}
      {config.label}
    </div>
  );
}
