import { useCallback, useEffect, useState, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Download,
  FileText,
  Loader2,
  XCircle,
} from 'lucide-react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CodeViewer } from '@/components/viewer/code-viewer';
import { DiagramViewer } from '@/components/viewer/diagram-viewer';
import { ExtractionTree } from '@/components/viewer/extraction-tree';
import { SummaryTabs } from '@/components/viewer/summary-tabs';
import { MarkdownDiagram } from '@/components/viewer/markdown-diagram';
import { papersApi } from '@/lib/api/papers';
import { pipelineApi } from '@/lib/api/pipeline';
import { usePipelineSSE } from '@/lib/hooks/use-pipeline-sse';
import { hasBundleOutputs, resolveViewerRunStatus, shouldStreamRun } from '@/lib/pipeline-status';
import { cn } from '@/lib/utils';
import { OutputBundle, Paper, PipelineRun, StageResult } from '@/types';

const STAGE_ORDER = [
  'ingest',
  'classify',
  'extract',
  'summarise',
  'embed',
  'diagram',
  'codegen',
  'report',
] as const;

const STAGE_LABELS: Record<string, string> = {
  ingest: 'Ingest',
  classify: 'Classify',
  extract: 'Extract',
  summarise: 'Summarize',
  embed: 'Embed',
  diagram: 'Diagram',
  codegen: 'Code',
  report: 'Report',
};

const initialLoadPromises = new Map<
  string,
  Promise<{ paper: Paper; bundle: OutputBundle; latestRun: PipelineRun | null }>
>();

import { supabase } from '@/lib/supabase';

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
  if (!stage?.started_at || !stage?.completed_at) return '-';
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

  const activeRun = (staticRun ?? null) as Partial<PipelineRun> | null;
  const { run: liveRun, done: runDone } = usePipelineSSE(
    shouldStreamRun(activeRun) ? pipelineRunId : null,
  );
  const resolvedRun = (liveRun ?? activeRun) as Partial<PipelineRun> | null;

  const refreshOutputs = useCallback(async () => {
    if (!id) return;
    const bundleData = await papersApi.getOutputBundle(id);
    setBundle(bundleData);
    if (bundleData.report) {
      try {
        setReportMarkdown(await papersApi.getReportMarkdown(id));
      } catch {
        setReportMarkdown('');
      }
    } else {
      setReportMarkdown('');
    }
  }, [id]);

  const refreshLatestRun = useCallback(async () => {
    if (!id) return;
    const latestRun = await pipelineApi.getLatestRunForPaper(id);
    setStaticRun(latestRun);
    setPipelineRunId(latestRun?.id ?? null);
  }, [id]);

  useEffect(() => {
    // Only check if it JUST finished to trigger a refresh
    if (
      runDone &&
      (resolvedRun?.status === 'completed' ||
        resolvedRun?.status === 'partial' ||
        resolvedRun?.status === 'failed') &&
        staticRun?.status !== resolvedRun.status
    ) {
      refreshLatestRun().catch(console.error);
      refreshOutputs().catch(console.error);
    }
  }, [refreshLatestRun, refreshOutputs, resolvedRun?.status, runDone, staticRun?.status]);

  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      try {
        let loadPromise = initialLoadPromises.get(id);
        if (!loadPromise) {
          loadPromise = Promise.all([
            papersApi.getPaper(id),
            papersApi.getOutputBundle(id),
            pipelineApi.getLatestRunForPaper(id),
          ]).then(([paperData, bundleData, latestRun]) => ({
            paper: paperData,
            bundle: bundleData,
            latestRun,
          }));
          initialLoadPromises.set(id, loadPromise);
        }

        const { paper: paperData, bundle: bundleData, latestRun } = await loadPromise;
        setPaper(paperData);
        setBundle(bundleData);
        setStaticRun(latestRun);
        setPipelineRunId(latestRun?.id ?? null);

        if (bundleData.report) {
          try {
            setReportMarkdown(await papersApi.getReportMarkdown(id));
          } catch {
            setReportMarkdown('');
          }
        } else {
          setReportMarkdown('');
        }
      } catch (error) {
        console.error('Failed to load paper:', error);
      } finally {
        initialLoadPromises.delete(id);
        setIsLoading(false);
      }
    };
    fetchData();
  }, [id]);

  const handleDownloadReport = useCallback(async () => {
    if (!id) return;
    try {
      const md = await papersApi.getReportMarkdown(id);
      downloadBlob(new Blob([md], { type: 'text/markdown' }), `${id}_report.md`);
    } catch {
      toast.error('Failed to download report');
    }
  }, [id]);

  const handleDownloadCode = useCallback(async () => {
    if (!id) return;
    try {
      const code = await papersApi.getCodeSource(id);
      downloadBlob(new Blob([code], { type: 'text/x-python' }), `${id}_implementation.py`);
    } catch {
      toast.error('Failed to download code');
    }
  }, [id]);

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

  if (isLoading) {
    return (
      <div className="flex flex-col h-screen">
        <div className="h-16 border-b border-[#1a1a1a] animate-pulse bg-secondary/20" />
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

  const runStatus = resolveViewerRunStatus(resolvedRun, bundle);
  const hasOutputs = hasBundleOutputs(bundle);
  const isRunActive = runStatus === 'pending' || runStatus === 'running';

  return (
    <div className="flex flex-col min-h-screen">
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
              {runStatus === 'running' || runStatus === 'pending' ? (
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
          {!hasOutputs && !isRunActive && (
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

      {!hasOutputs ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center mx-auto">
              {isRunActive ? (
                <Loader2 className="w-8 h-8 text-muted-foreground animate-spin" />
              ) : (
                <FileText className="w-8 h-8 text-muted-foreground" />
              )}
            </div>
            <p className="text-muted-foreground text-sm">
              {isRunActive
                ? 'Pipeline is running. Outputs will appear here as stages finish.'
                : 'No outputs yet. Run the pipeline to generate analysis.'}
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex gap-8 p-8 max-w-[1600px] mx-auto w-full overflow-hidden">
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
                      pythonPath={bundle!.code.python_path}
                      syntheticData={bundle!.code.synthetic_data_description ?? ''}
                    />
                  ) : (
                    <p className="text-muted-foreground text-sm">Code not yet generated.</p>
                  )}
                </TabsContent>
                <TabsContent value="report" className="mt-0">
                  {reportMarkdown ? (
                    <div className="prose prose-invert max-w-none markdown-body">
                      <Markdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          img: ({ node, ...props }) => {
                            if (props.src && !props.src.startsWith('http') && !props.src.startsWith('data:')) {
                              const { data } = supabase.storage.from('outputs').getPublicUrl(props.src);
                              return <img {...props} src={data.publicUrl} />;
                            }
                           ,
                          code: ({ node, inline, className, children, ...props }: any) => {
                            const match = /language-(\w+)/.exec(className || '');
                            if (!inline && match && match[1] === 'mermaid') {
                              return <MarkdownDiagram code={String(children).replace(/\n$/, '')} />;
                            }
                            return (
                              <code className={className} {...props}>
                                {children}
                              </code>
                            );
                          } return <img {...props} />;
                          }
                        }}
                      >
                        {reportMarkdown}
                      </Markdown>
                    </div>
                  ) : bundle!.report ? (
                    <p className="text-muted-foreground text-sm">Loading report...</p>
                  ) : (
                    <p className="text-muted-foreground text-sm">Report not yet generated.</p>
                  )}
                </TabsContent>
              </div>
            </Tabs>
          </div>

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

      {resolvedRun && (
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
              const stages = resolvedRun.stages ?? {};
              const stage = stages[stageKey];
              const status = stage?.status;
              const color =
                status === 'completed'
                  ? 'bg-green-500'
                  : status === 'cached'
                  ? 'bg-blue-500'
                  : status === 'failed'
                  ? 'bg-destructive'
                  : status === 'running'
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
                      {status === 'cached' ? 'CACHED' : stageDuration(stage)}
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
