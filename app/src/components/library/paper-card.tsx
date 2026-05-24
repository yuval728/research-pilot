import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronRight, Code2, FileText, GitBranch, Globe, Lock, Upload } from 'lucide-react';
import { Paper, PipelineRun } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { toDisplayStatus } from '@/lib/pipeline-status';
import { cn } from '@/lib/utils';
import { formatDate } from '@/lib/utils/format';
import { papersApi } from '@/lib/api/papers';
import { toast } from 'sonner';

interface PaperCardProps {
  paper: Paper;
  pipelineRun?: PipelineRun | null;
  /** Called with the updated Paper after a successful publish. */
  onPublish?: (updated: Paper) => void;
  /** Called after a successful import of a public paper. */
  onImport?: (paperId: string) => void;
}

type DisplayStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export function PaperCard({ paper, pipelineRun, onPublish, onImport }: PaperCardProps) {
  const navigate = useNavigate();
  const status = toDisplayStatus(pipelineRun);
  const displayStatus: DisplayStatus =
    status === 'PENDING' && paper.imported_from_paper_id ? 'COMPLETED' : status;
  const meta = paper.metadata;
  const [isPublishing, setIsPublishing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);

  const handlePublish = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (isPublishing) return;
    setIsPublishing(true);
    try {
      const updated = await papersApi.publishPaper(paper.id);
      onPublish?.(updated);
    } catch (err) {
      console.error('Failed to publish paper:', err);
    } finally {
      setIsPublishing(false);
    }
  };

  const canPublish = !paper.is_public && displayStatus === 'COMPLETED' && !!onPublish;
  const canImport = paper.is_public && !!onImport;

  return (
    <Card className="bg-card border-border hover:border-primary/60 transition-all group overflow-hidden h-full">
      <CardHeader className="p-5 pb-3">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex gap-2 flex-wrap max-w-[70%]">
            {meta?.domain && (
              <Badge
                variant="secondary"
                className="bg-secondary/70 text-foreground/80 text-[10px] font-bold uppercase tracking-wider border-none"
              >
                {meta.domain}
              </Badge>
            )}
            {meta?.sub_domain && (
              <Badge
                variant="secondary"
                className="bg-primary/15 text-primary text-[10px] font-bold uppercase tracking-wider border-none"
              >
                {meta.sub_domain}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <VisibilityBadge
              isPublic={paper.is_public}
              isImported={Boolean(paper.imported_from_paper_id)}
            />
            <StatusBadge status={displayStatus} />
          </div>
        </div>
        <h3 className="text-base font-semibold leading-tight line-clamp-2 group-hover:text-primary transition-colors">
          {meta?.title ?? 'Untitled Paper'}
        </h3>
        {meta?.authors && meta.authors.length > 0 && (
          <p className="text-sm text-muted-foreground truncate mt-1">{meta.authors.join(', ')}</p>
        )}
        <div className="flex items-center gap-2 mt-2 text-[10px] text-muted-foreground font-medium uppercase tracking-widest">
          <span>Added {formatDate(paper.created_at)}</span>
          {(meta?.venue || meta?.year) && <span>-</span>}
          {meta?.venue && <span>{meta.venue}</span>}
          {meta?.venue && meta?.year && <span>-</span>}
          {meta?.year && <span>{meta.year}</span>}
        </div>
      </CardHeader>

      <CardContent className="p-5 pt-0 flex-1">
        {displayStatus === 'RUNNING' ? (
          <div className="flex items-center gap-3 py-2">
            <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary animate-progress-indeterminate" />
            </div>
            <span className="text-[10px] font-bold text-primary animate-pulse">PROCESSING</span>
          </div>
        ) : displayStatus === 'FAILED' ? (
          <div className="bg-destructive/10 text-destructive text-[10px] font-bold p-2 rounded border border-destructive/20">
            PIPELINE FAILED
          </div>
        ) : displayStatus === 'PENDING' ? (
          <div className="bg-muted/30 text-muted-foreground text-[10px] font-bold p-2 rounded border border-muted/20">
            AWAITING PIPELINE
          </div>
        ) : (
          <div className="flex items-center justify-between gap-1">
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-primary/70"
                title="View diagrams"
                onClick={() => navigate(`/papers/${paper.id}?tab=diagrams`)}
              >
                <GitBranch className="w-4 h-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-primary/70"
                title="View code"
                onClick={() => navigate(`/papers/${paper.id}?tab=code`)}
              >
                <Code2 className="w-4 h-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-primary/70"
                title="View report"
                onClick={() => navigate(`/papers/${paper.id}?tab=report`)}
              >
                <FileText className="w-4 h-4" />
              </Button>
            </div>

            {canPublish && (
              <Button
                variant="outline"
                size="sm"
                disabled={isPublishing}
                onClick={handlePublish}
                className="h-7 text-[10px] font-bold uppercase tracking-wider gap-1.5 border-primary/40 text-primary hover:bg-primary/10 hover:border-primary transition-colors"
                title="Make this paper visible to everyone"
              >
                <Upload className={cn('w-3 h-3', isPublishing && 'animate-pulse')} />
                {isPublishing ? 'Publishing…' : 'Publish'}
              </Button>
            )}

            {canImport && !canPublish && (
              <Button
                variant="outline"
                size="sm"
                disabled={isImporting}
                onClick={async (e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  if (isImporting) return;
                  setIsImporting(true);
                  try {
                    await papersApi.importPaper(paper.id);
                    onImport?.(paper.id);
                  } catch (err) {
                    console.error('Failed to import paper:', err);
                    toast.error('Failed to import paper');
                  } finally {
                    setIsImporting(false);
                  }
                }}
                className="h-7 text-[10px] font-bold uppercase tracking-wider gap-1.5 border-primary/40 text-primary hover:bg-primary/10 hover:border-primary transition-colors"
                title="Import this paper into your library"
              >
                <Upload className={cn('w-3 h-3', isImporting && 'animate-pulse')} />
                {isImporting ? 'Importing…' : 'Import'}
              </Button>
            )}
          </div>
        )}
      </CardContent>

      <CardFooter className="p-0 border-t border-border">
        <Link
          to={`/papers/${paper.id}`}
          className="w-full flex items-center justify-between px-5 py-3 text-xs font-bold uppercase tracking-widest hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
        >
          View Analysis
          <ChevronRight className="w-4 h-4" />
        </Link>
      </CardFooter>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function VisibilityBadge({
  isPublic,
  isImported,
}: {
  isPublic: boolean;
  isImported: boolean;
}) {
  if (isImported) {
    return (
      <div
        title="Imported — copied from the public library"
        className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter transition-colors bg-primary/15 text-primary"
      >
        <Upload className="w-2.5 h-2.5" />
        Imported
      </div>
    );
  }

  return (
    <div
      title={isPublic ? 'Public — visible to all users' : 'Private — only you can see this'}
      className={cn(
        'flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-black uppercase tracking-tighter transition-colors',
        isPublic
          ? 'bg-emerald-500/10 text-emerald-500'
          : 'bg-muted/60 text-muted-foreground',
      )}
    >
      {isPublic ? <Globe className="w-2.5 h-2.5" /> : <Lock className="w-2.5 h-2.5" />}
      {isPublic ? 'Public' : 'Private'}
    </div>
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
