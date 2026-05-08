import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Download,
  CheckCircle2,
  Clock,
  XCircle,
  Loader2,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ExtractionTree } from '@/components/viewer/extraction-tree';
import { SummaryTabs } from '@/components/viewer/summary-tabs';
import { DiagramViewer } from '@/components/viewer/diagram-viewer';
import { CodeViewer } from '@/components/viewer/code-viewer';
import { papersApi } from '@/lib/api/papers';
import { pipelineApi } from '@/lib/api/pipeline';
import { Paper, OutputBundle, PipelineRun, StageResult } from '@/types';
import { cn } from '@/lib/utils';
import Markdown from 'react-markdown';
import { toast } from 'sonner';
import { usePipelineSSE } from '@/lib/hooks/use-pipeline-sse';

// Canonical stage order matching the backend pipeline
const STAGE_ORDER = [
  'ingest', 'classify', 'extract', 'summarise',
  'embed', 'diagram', 'codegen', 'report',
] as const;

const STAGE_LABELS: Record<string, string> = {
  ingest: 'Ingest', classify: 'Classify', extract: 'Extract',
  summarise: 'Summarize', embed: 'Embed', diagram: 'Diagram',
  codegen: 'Code', report: 'Report',
};

/** Trigger a file download in the browser. */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function stageDuration(stage: StageResult | undefined): string {
  if (!stage?.started_at || !stage?.completed_at) return '—';
  const secs =
    (new Date(stage.completed_at).getTime() - new Date(stage.started_at).getTime()) / 1000;
  return `${secs.toFixed(1)}s`;
}

export default function PaperViewerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [paper, setPaper] = useState<Paper | null>(null);
  const [bundle, setBundle] = useState<OutputBundle | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState('');
  const [staticRun, setStaticRun] = useState<PipelineRun | null>(null);
  const [pipelineRunId, setPipelineRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Live pipeline updates
  const { run: liveRun, done: runDone } = usePipelineSSE(pipelineRunId);
  const activeRun = (liveRun ?? staticRun) as Partial<PipelineRun> | null;

  // Auto-fetch bundle when pipeline completes
  useEffect(() => {
    if (runDone && (activeRun?.status === 'completed' || activeRun?.status === 'partial')) {
      if (!id) return;
      papersApi.getOutputBundle(id).then(setBundle).catch(console.error);
      papersApi.getReportMarkdown(id).then(setReportMarkdown).catch(() => {});
    }
  }, [runDone, activeRun?.status, id]);

  // ── Initial data fetch ──────────────────────────────────────────────────
  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      try {
        const [paperData, bundleData] = await Promise.all([
          papersApi.getPaper(id),
          papersApi.getOutputBundle(id),
        ]);
        setPaper(paperData);
        setBundle(bundleData);

        // Fetch report markdown if available
        if (bundleData.report) {
          try {
            const md = await papersApi.getReportMarkdown(id);
            setReportMarkdown(md);
          } catch {
            // Report might not be ready yet
          }
        }
      } catch (error) {
        console.error('Failed to load paper:', error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [id]);

  // ── Download handlers ───────────────────────────────────────────────────
  const handleDownloadReport = useCallback(async () => {
    if (!id) return;
    try {
      const md = await papersApi.getReportMarkdown(id);
      const blob = new Blob([md], { type: 'text/markdown' });
      downloadBlob(blob, `${id}_report.md`);
    } catch {
      toast.error('Failed to download report');
    }
  }, [id]);

  const handleDownloadCode = useCallback(async () => {
    if (!id) return;
    try {
      const code = await papersApi.getCodeSource(id);
      const blob = new Blob([code], { type: 'text/x-python' });
      downloadBlob(blob, `${id}_implementation.py`);
    } catch {
      toast.error('Failed to download code');
    }
  }, [id]);

  const handleDownloadNotebook = useCallback(async () => {
    if (!id) return;
    try {
      const blob = await papersApi.getNotebook(id);
      downloadBlob(blob, `${id}_notebook.ipynb`);
    } catch {
      toast.error('Failed to download notebook');
    }
  }, [id]);

  // ── Run pipeline if no outputs yet ─────────────────────────────────────
  const handleTriggerPipeline = useCallback(async () => {
    if (!id) return;
    try {
      const run = await pipelineApi.triggerRun(id);
      setStaticRun(run);
      setPipelineRunId(run.id);
      toast.success('Pipeline started!');
    } catch (err: any) {
      toast.error(err?.body?.detail ?? 'Failed to start pipeline');
    }
  }, [id]);

  // ── Loading skeleton ────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex flex-col h-screen">
        <div className="h-16 border-b border-[#1a1a1a] animate-pulse bg-secondary/20" />
        <div className="flex-1 p-8 flex gap-8">
          <div className="flex-[0.65] space-y-8">
            <div className="h-12 w-1/2 bg-secondary/20 rounded-lg animate-pulse" />
            <div className="h-64 bg-secondary/20 rounded-xl animate-pulse" />
          </div>
          <div className="flex-[0.35] bg-secondary/10 rounded-xl animate-pulse" />
        </div>
      </div>
    );
  }

  if (!paper) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <p className="text-muted-foreground">Paper not found</p>
        <Button onClick={() => navigate('/library')}>Back to Library</Button>
      </div>
    );
  }

  const runStatus = activeRun?.status ?? 'completed';
  const hasOutputs =
    bundle && (bundle.summaries.length > 0 || bundle.diagrams.length > 0 || bundle.report);

  return (
    <div className="flex flex-col min-h-screen">
      {/* ── Sticky header ── */}
      <header className="border-b border-[#1a1a1a] bg-background/50 backdrop-blur-md sticky top-0 z-20">
        <div className="px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Button
              variant="ghost"
              size="sm"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => navigate('/library')}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Library
            </Button>
            <div className="space-y-1">
              <h1 className="text-xl font-bold tracking-tight">
                {paper.metadata?.title ?? 'Untitled Paper'}
              </h1>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span>{paper.metadata?.authors?.join(', ')}</span>
                {paper.metadata?.venue && (
                  <>
                    <span>•</span>
                    <span>
                      {paper.metadata.venue} {paper.metadata.year}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {paper.metadata?.sub_domain && (
              <Badge
                variant="secondary"
                className="bg-primary/10 text-primary border-none font-bold uppercase tracking-widest text-[10px]"
              >
                {paper.metadata.sub_domain}
              </Badge>
            )}
            <div
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded-full text-[9px] font-black uppercase tracking-tighter',
                runStatus === 'completed'
                  ? 'bg-green-500/10 text-green-500'
                  : runStatus === 'running' || runStatus === 'pending'
                  ? 'bg-primary/10 text-primary'
                  : runStatus === 'failed'
                  ? 'bg-destructive/10 text-destructive'
                  : 'bg-green-500/10 text-green-500',
              )}
            >
              {runStatus === 'running' ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : runStatus === 'failed' ? (
                <XCircle className="w-3 h-3" />
              ) : (
                <CheckCircle2 className="w-3 h-3" />
              )}
              {runStatus.toUpperCase()}
            </div>
          </div>
        </div>

        {/* Download actions */}
        <div className="px-8 pb-4 flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest"
            disabled={!bundle?.report}
            onClick={handleDownloadReport}
          >
            <Download className="w-3.5 h-3.5 mr-2" />
            Report (MD)
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest"
            disabled={!bundle?.code?.python_path}
            onClick={handleDownloadCode}
          >
            <Download className="w-3.5 h-3.5 mr-2" />
            Code (.PY)
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest"
            disabled={!bundle?.code?.notebook_path}
            onClick={handleDownloadNotebook}
          >
            <Download className="w-3.5 h-3.5 mr-2" />
            Notebook (.IPYNB)
          </Button>
          {!hasOutputs && (
            <Button
              size="sm"
              className="h-8 bg-primary text-[10px] font-bold uppercase tracking-widest ml-auto"
              onClick={handleTriggerPipeline}
            >
              Run Pipeline
            </Button>
          )}
        </div>
      </header>

      {/* ── Body ── */}
      {!hasOutputs ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mx-auto">
              <Loader2 className="w-8 h-8 text-muted-foreground" />
            </div>
            <p className="text-muted-foreground text-sm">
              No outputs yet. Run the pipeline to generate analysis.
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex gap-8 p-8 max-w-[1600px] mx-auto w-full overflow-hidden">
          {/* Main content */}
          <div className="flex-[0.65] min-w-0">
            <Tabs defaultValue="summary" className="w-full">
              <TabsList className="bg-transparent border-b border-[#1a1a1a] w-full justify-start rounded-none h-12 p-0 gap-8">
                {[
                  { value: 'summary', label: 'Summary' },
                  { value: 'diagrams', label: 'Diagrams' },
                  { value: 'code', label: 'Code' },
                  { value: 'report', label: 'Full Report' },
                ].map(({ value, label }) => (
                  <TabsTrigger
                    key={value}
                    value={value}
                    className="data-[state=active]:border-primary data-[state=active]:text-primary border-b-2 border-transparent rounded-none bg-transparent px-0 font-bold text-[10px] uppercase tracking-[0.2em]"
                  >
                    {label}
                  </TabsTrigger>
                ))}
              </TabsList>

              <div className="py-8">
                <TabsContent value="summary" className="mt-0">
                  {bundle!.summaries.length > 0 ? (
                    <SummaryTabs summaries={bundle!.summaries} />
                  ) : (
                    <p className="text-muted-foreground text-sm">Summaries not yet generated.</p>
                  )}
                </TabsContent>

                <TabsContent value="diagrams" className="mt-0">
                  {bundle!.diagrams.length > 0 ? (
                    <DiagramViewer diagrams={bundle!.diagrams} />
                  ) : (
                    <p className="text-muted-foreground text-sm">Diagrams not yet generated.</p>
                  )}
                </TabsContent>

                <TabsContent value="code" className="mt-0">
                  {bundle!.code ? (
                    <CodeViewer
                      paperId={id!}
                      syntheticData={bundle!.code.synthetic_data_description ?? ''}
                    />
                  ) : (
                    <p className="text-muted-foreground text-sm">Code not yet generated.</p>
                  )}
                </TabsContent>

                <TabsContent value="report" className="mt-0">
                  {reportMarkdown ? (
                    <div className="prose prose-invert max-w-none markdown-body">
                      <Markdown>{reportMarkdown}</Markdown>
                    </div>
                  ) : bundle!.report ? (
                    <p className="text-muted-foreground text-sm">Loading report…</p>
                  ) : (
                    <p className="text-muted-foreground text-sm">Report not yet generated.</p>
                  )}
                </TabsContent>
              </div>
            </Tabs>
          </div>

          {/* Sidebar */}
          <div className="flex-[0.35] min-w-[320px]">
            <div className="bg-[#0f0f0f] border border-[#1a1a1a] rounded-xl p-6 sticky top-40 h-[calc(100vh-12rem)] overflow-y-auto custom-scrollbar">
              {bundle!.extraction ? (
                <ExtractionTree data={bundle!.extraction} />
              ) : (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  Extraction data not yet available.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Pipeline Timeline */}
      {activeRun && (
        <div className="px-8 py-6 border-t border-[#1a1a1a] bg-[#050505]">
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Pipeline Execution Timeline
            </h4>
            <div className="flex gap-4 text-[10px] font-bold text-muted-foreground">
              <span className="flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-green-500" /> Completed
              </span>
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3 text-blue-500" /> Cached
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {STAGE_ORDER.map((stageKey) => {
              const stages = activeRun.stages ?? {};
              const stage = stages[stageKey];
              const s = stage?.status;
              const color =
                s === 'completed'
                  ? 'bg-green-500'
                  : s === 'cached'
                  ? 'bg-blue-500'
                  : s === 'failed'
                  ? 'bg-destructive'
                  : s === 'running'
                  ? 'bg-primary animate-pulse'
                  : 'bg-muted';
              return (
                <div key={stageKey} className="flex-1 flex flex-col gap-2">
                  <div className={cn('h-1 rounded-full', color)} />
                  <div className="flex items-center justify-between px-1">
                    <span className="text-[9px] font-bold uppercase tracking-tighter text-muted-foreground">
                      {STAGE_LABELS[stageKey]}
                    </span>
                    <span className="text-[9px] font-medium text-muted-foreground/50">
                      {s === 'cached' ? 'CACHED' : stageDuration(stage)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
