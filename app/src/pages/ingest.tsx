import { useState, useRef, useCallback } from 'react';
import {
  Upload,
  Link as LinkIcon,
  Hash,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronRight,
  FileText,
} from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { papersApi } from '@/lib/api/papers';
import { pipelineApi } from '@/lib/api/pipeline';
import { usePipelineSSE } from '@/lib/hooks/use-pipeline-sse';
import { Paper, PipelineRun, StageResult } from '@/types';

// Canonical stage order from the backend pipeline
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

function getStageStatus(stage: StageResult | undefined): 'completed' | 'running' | 'failed' | 'pending' | 'cached' {
  if (!stage) return 'pending';
  if (stage.status === 'completed') return 'completed';
  if (stage.status === 'cached') return 'cached';
  if (stage.status === 'running') return 'running';
  if (stage.status === 'failed') return 'failed';
  return 'pending';
}

function formatDuration(stage: StageResult | undefined): string | null {
  if (!stage?.started_at || !stage?.completed_at) return null;
  const secs = (new Date(stage.completed_at).getTime() - new Date(stage.started_at).getTime()) / 1000;
  return `${secs.toFixed(1)}s`;
}

export default function IngestPage() {
  const navigate = useNavigate();

  // Input state
  const [activeTab, setActiveTab] = useState<'upload' | 'arxiv' | 'doi'>('upload');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [arxivInput, setArxivInput] = useState('');
  const [doiInput, setDoiInput] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);

  // Live run data from SSE
  const { run, done } = usePipelineSSE(runId);

  // Compute progress from real stage data
  const stages = run?.stages ?? {};
  const completedCount = STAGE_ORDER.filter((s) => {
    const st = stages[s]?.status;
    return st === 'completed' || st === 'cached';
  }).length;
  const progress = (completedCount / STAGE_ORDER.length) * 100;

  // Navigate when pipeline completes
  const navigatedRef = useRef(false);
  if (done && paper && !navigatedRef.current && (run?.status === 'completed' || run?.status === 'partial')) {
    navigatedRef.current = true;
    setTimeout(() => navigate(`/papers/${paper.id}`), 800);
  }

  // ── File drag & drop ────────────────────────────────────────────────────
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file?.type === 'application/pdf') {
      setSelectedFile(file);
    } else {
      toast.error('Only PDF files are accepted');
    }
  }, []);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSelectedFile(file);
  }, []);

  // ── Main ingest flow ────────────────────────────────────────────────────
  const handleProcess = async () => {
    setIngestError(null);
    navigatedRef.current = false;

    try {
      setIsProcessing(true);
      let createdPaper: Paper;

      // Step 1: Ingest paper via chosen method
      if (activeTab === 'upload') {
        if (!selectedFile) {
          toast.error('Please select a PDF file first');
          setIsProcessing(false);
          return;
        }
        createdPaper = await papersApi.uploadPaper(selectedFile);
      } else if (activeTab === 'arxiv') {
        if (!arxivInput.trim()) {
          toast.error('Please enter an arXiv URL or ID');
          setIsProcessing(false);
          return;
        }
        // Normalise plain IDs like "1706.03762" to full URLs
        const url = arxivInput.startsWith('http')
          ? arxivInput.trim()
          : `https://arxiv.org/abs/${arxivInput.trim()}`;
        createdPaper = await papersApi.createFromArxiv(url);
      } else {
        if (!doiInput.trim()) {
          toast.error('Please enter a DOI');
          setIsProcessing(false);
          return;
        }
        createdPaper = await papersApi.createFromDoi(doiInput.trim());
      }

      setPaper(createdPaper);

      // Step 2: Trigger pipeline run
      const pipelineRun: PipelineRun = await pipelineApi.triggerRun(createdPaper.id);
      setRunId(pipelineRun.id);
      toast.success('Pipeline started!');
    } catch (err: any) {
      const msg = err?.body?.detail ?? err?.message ?? 'Failed to start processing';
      setIngestError(msg);
      toast.error(msg);
      setIsProcessing(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col min-h-screen">
      <Header title="Add Paper" />

      <div className="p-8 max-w-3xl mx-auto w-full space-y-8">
        <div className="space-y-1">
          <h2 className="text-2xl font-bold tracking-tight">Process Paper</h2>
          <p className="text-muted-foreground text-sm">
            Process a research paper through the AI intelligence pipeline
          </p>
        </div>

        {!isProcessing ? (
          <div className="space-y-6">
            <Tabs
              value={activeTab}
              onValueChange={(v) => setActiveTab(v as typeof activeTab)}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-3 bg-[#0f0f0f] border border-[#1a1a1a] p-1 h-12">
                <TabsTrigger
                  value="upload"
                  className="data-[state=active]:bg-secondary data-[state=active]:text-primary font-bold text-[10px] uppercase tracking-widest"
                >
                  <Upload className="w-3.5 h-3.5 mr-2" />
                  Upload PDF
                </TabsTrigger>
                <TabsTrigger
                  value="arxiv"
                  className="data-[state=active]:bg-secondary data-[state=active]:text-primary font-bold text-[10px] uppercase tracking-widest"
                >
                  <LinkIcon className="w-3.5 h-3.5 mr-2" />
                  arXiv URL
                </TabsTrigger>
                <TabsTrigger
                  value="doi"
                  className="data-[state=active]:bg-secondary data-[state=active]:text-primary font-bold text-[10px] uppercase tracking-widest"
                >
                  <Hash className="w-3.5 h-3.5 mr-2" />
                  DOI
                </TabsTrigger>
              </TabsList>

              {/* ── Upload Tab ── */}
              <TabsContent value="upload" className="mt-6">
                <div
                  className={cn(
                    'border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center text-center space-y-4 cursor-pointer bg-[#0f0f0f]/50 transition-colors',
                    isDragging
                      ? 'border-primary/80 bg-primary/5'
                      : selectedFile
                      ? 'border-green-500/50 bg-green-500/5'
                      : 'border-[#1a1a1a] hover:border-primary/50',
                  )}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf"
                    className="hidden"
                    onChange={handleFileChange}
                  />
                  <div className="w-12 h-12 bg-secondary rounded-full flex items-center justify-center text-muted-foreground">
                    {selectedFile ? (
                      <FileText className="w-6 h-6 text-green-500" />
                    ) : (
                      <Upload className="w-6 h-6" />
                    )}
                  </div>
                  <div className="space-y-1">
                    {selectedFile ? (
                      <>
                        <p className="font-semibold text-green-400">{selectedFile.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {(selectedFile.size / 1024 / 1024).toFixed(2)} MB · Click to change
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="font-semibold">Drop a PDF here or click to browse</p>
                        <p className="text-xs text-muted-foreground">Max 50 pages · PDF only</p>
                      </>
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* ── arXiv Tab ── */}
              <TabsContent value="arxiv" className="mt-6 space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    arXiv URL or ID
                  </label>
                  <Input
                    value={arxivInput}
                    onChange={(e) => setArxivInput(e.target.value)}
                    placeholder="https://arxiv.org/abs/1706.03762 or 1706.03762"
                    className="bg-[#0f0f0f] border-[#1a1a1a] py-6"
                  />
                </div>
              </TabsContent>

              {/* ── DOI Tab ── */}
              <TabsContent value="doi" className="mt-6 space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    DOI
                  </label>
                  <Input
                    value={doiInput}
                    onChange={(e) => setDoiInput(e.target.value)}
                    placeholder="10.1234/example.doi"
                    className="bg-[#0f0f0f] border-[#1a1a1a] py-6"
                  />
                </div>
              </TabsContent>
            </Tabs>

            {ingestError && (
              <div className="flex items-start gap-3 bg-destructive/10 border border-destructive/30 rounded-lg p-4 text-sm text-destructive">
                <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{ingestError}</span>
              </div>
            )}

            <Button
              className="w-full bg-primary hover:bg-primary/90 py-7 text-base font-bold uppercase tracking-widest"
              onClick={handleProcess}
            >
              Process Paper
            </Button>
          </div>
        ) : (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Paper info + overall progress */}
            <Card className="bg-[#0f0f0f] border-[#1a1a1a] overflow-hidden">
              <CardContent className="p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <h3 className="font-bold">
                      {paper?.metadata?.title ?? 'Processing…'}
                    </h3>
                    {paper?.metadata && (
                      <p className="text-xs text-muted-foreground">
                        {paper.metadata.authors?.join(', ')}{' '}
                        {paper.metadata.year ? `· ${paper.metadata.year}` : ''}
                        {paper.metadata.venue ? ` · ${paper.metadata.venue}` : ''}
                      </p>
                    )}
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-black text-primary">{Math.round(progress)}%</p>
                    <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                      Overall Progress
                    </p>
                  </div>
                </div>
                <Progress value={progress} className="h-2 bg-muted" />
                {run?.status === 'failed' && run.error && (
                  <div className="flex items-start gap-2 text-destructive text-sm bg-destructive/10 rounded-lg p-3 border border-destructive/20">
                    <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                    <span>{run.error}</span>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Per-stage breakdown */}
            <div className="space-y-4">
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">
                Pipeline Stages
              </h4>
              <div className="space-y-3">
                {STAGE_ORDER.map((stageKey) => {
                  const stageData = stages[stageKey];
                  const status = getStageStatus(stageData);
                  const isCompleted = status === 'completed' || status === 'cached';
                  const isCurrent = status === 'running';
                  const isFailed = status === 'failed';
                  const duration = formatDuration(stageData);

                  return (
                    <div
                      key={stageKey}
                      className={cn(
                        'flex items-center justify-between p-4 rounded-lg border transition-all duration-300',
                        isCompleted
                          ? 'bg-green-500/5 border-green-500/20'
                          : isCurrent
                          ? 'bg-primary/5 border-primary/30 shadow-[0_0_15px_rgba(99,102,241,0.1)]'
                          : isFailed
                          ? 'bg-destructive/5 border-destructive/20'
                          : 'bg-[#0f0f0f] border-[#1a1a1a] opacity-50',
                      )}
                    >
                      <div className="flex items-center gap-4">
                        <div
                          className={cn(
                            'w-6 h-6 rounded-full flex items-center justify-center',
                            isCompleted
                              ? 'bg-green-500 text-white'
                              : isCurrent
                              ? 'bg-primary text-white'
                              : isFailed
                              ? 'bg-destructive text-white'
                              : 'bg-muted text-muted-foreground',
                          )}
                        >
                          {isCompleted ? (
                            <CheckCircle2 className="w-4 h-4" />
                          ) : isCurrent ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : isFailed ? (
                            <XCircle className="w-4 h-4" />
                          ) : (
                            <div className="w-1.5 h-1.5 bg-current rounded-full" />
                          )}
                        </div>
                        <div>
                          <span
                            className={cn(
                              'font-semibold text-sm',
                              isCurrent && 'text-primary',
                              isFailed && 'text-destructive',
                            )}
                          >
                            {STAGE_LABELS[stageKey] ?? stageKey}
                          </span>
                          {status === 'cached' && (
                            <span className="ml-2 text-[9px] font-bold text-blue-400 uppercase tracking-wider">
                              CACHED
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="text-right">
                        {duration && isCompleted && (
                          <span className="text-[10px] font-bold text-muted-foreground">{duration}</span>
                        )}
                        {isCurrent && (
                          <span className="text-[10px] font-bold text-primary animate-pulse uppercase tracking-widest">
                            Running
                          </span>
                        )}
                        {isFailed && stageData?.error_message && (
                          <span className="text-[10px] font-bold text-destructive max-w-[160px] text-right truncate block">
                            {stageData.error_message}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Navigate to results once done */}
            {done && paper && run?.status === 'completed' && (
              <Button
                className="w-full bg-primary hover:bg-primary/90 py-7 text-base font-bold uppercase tracking-widest animate-in zoom-in duration-500"
                onClick={() => navigate(`/papers/${paper.id}`)}
              >
                View Results
                <ChevronRight className="w-5 h-5 ml-2" />
              </Button>
            )}
            {done && run?.status === 'failed' && (
              <Button
                variant="outline"
                className="w-full border-destructive/30 text-destructive hover:bg-destructive/10 py-7 text-base font-bold uppercase tracking-widest"
                onClick={() => {
                  setIsProcessing(false);
                  setRunId(null);
                  setIngestError(null);
                }}
              >
                Try Again
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
