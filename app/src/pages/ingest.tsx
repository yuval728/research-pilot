import { useState } from 'react';
import { Upload, Link as LinkIcon, Hash, CheckCircle2, XCircle, Loader2, ChevronRight } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

export default function IngestPage() {
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState(0);
  const navigate = useNavigate();

  const stages = [
    { name: 'Ingest', duration: '1.2s' },
    { name: 'Classify', duration: '0.8s' },
    { name: 'Extract', duration: '4.5s' },
    { name: 'Summarize', duration: '2.1s' },
    { name: 'Embed', duration: '1.5s' },
    { name: 'Diagram', duration: '3.2s' },
    { name: 'Code', duration: '5.4s' },
    { name: 'Report', duration: '1.1s' },
  ];

  const handleProcess = () => {
    setIsProcessing(true);
    let stage = 0;
    const interval = setInterval(() => {
      stage++;
      setCurrentStage(stage);
      setProgress((stage / stages.length) * 100);
      if (stage >= stages.length) {
        clearInterval(interval);
        toast.success('Paper processed successfully!');
      }
    }, 1500);
  };

  return (
    <div className="flex flex-col min-h-screen">
      <Header title="Add Paper" />

      <div className="p-8 max-w-3xl mx-auto w-full space-y-8">
        <div className="space-y-1">
          <h2 className="text-2xl font-bold tracking-tight">Process Paper</h2>
          <p className="text-muted-foreground text-sm">Process a research paper through the AI intelligence pipeline</p>
        </div>

        {!isProcessing ? (
          <div className="space-y-6">
            <Tabs defaultValue="upload" className="w-full">
              <TabsList className="grid w-full grid-cols-3 bg-[#0f0f0f] border border-[#1a1a1a] p-1 h-12">
                <TabsTrigger value="upload" className="data-[state=active]:bg-secondary data-[state=active]:text-primary font-bold text-[10px] uppercase tracking-widest">
                  <Upload className="w-3.5 h-3.5 mr-2" />
                  Upload PDF
                </TabsTrigger>
                <TabsTrigger value="arxiv" className="data-[state=active]:bg-secondary data-[state=active]:text-primary font-bold text-[10px] uppercase tracking-widest">
                  <LinkIcon className="w-3.5 h-3.5 mr-2" />
                  arXiv URL
                </TabsTrigger>
                <TabsTrigger value="doi" className="data-[state=active]:bg-secondary data-[state=active]:text-primary font-bold text-[10px] uppercase tracking-widest">
                  <Hash className="w-3.5 h-3.5 mr-2" />
                  DOI
                </TabsTrigger>
              </TabsList>

              <TabsContent value="upload" className="mt-6">
                <div className="border-2 border-dashed border-[#1a1a1a] hover:border-primary/50 transition-colors rounded-xl p-12 flex flex-col items-center justify-center text-center space-y-4 cursor-pointer bg-[#0f0f0f]/50">
                  <div className="w-12 h-12 bg-secondary rounded-full flex items-center justify-center text-muted-foreground">
                    <Upload className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <p className="font-semibold">Drop a PDF here or click to browse</p>
                    <p className="text-xs text-muted-foreground">Max 50 pages • PDF only</p>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="arxiv" className="mt-6 space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">arXiv URL or ID</label>
                  <Input placeholder="https://arxiv.org/abs/1706.03762 or 1706.03762" className="bg-[#0f0f0f] border-[#1a1a1a] py-6" />
                </div>
              </TabsContent>

              <TabsContent value="doi" className="mt-6 space-y-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">DOI</label>
                  <Input placeholder="10.1234/example.doi" className="bg-[#0f0f0f] border-[#1a1a1a] py-6" />
                </div>
              </TabsContent>
            </Tabs>

            <Button className="w-full bg-primary hover:bg-primary/90 py-7 text-base font-bold uppercase tracking-widest" onClick={handleProcess}>
              Process Paper
            </Button>
          </div>
        ) : (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <Card className="bg-[#0f0f0f] border-[#1a1a1a] overflow-hidden">
              <CardContent className="p-6 space-y-6">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <h3 className="font-bold">Attention Is All You Need</h3>
                    <p className="text-xs text-muted-foreground">Vaswani et al. • 2017 • NeurIPS</p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-black text-primary">{Math.round(progress)}%</p>
                    <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">Overall Progress</p>
                  </div>
                </div>
                <Progress value={progress} className="h-2 bg-muted" />
              </CardContent>
            </Card>

            <div className="space-y-4">
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground ml-1">Pipeline Stages</h4>
              <div className="space-y-3">
                {stages.map((stage, index) => {
                  const isCompleted = index < currentStage;
                  const isCurrent = index === currentStage;
                  const isPending = index > currentStage;

                  return (
                    <div key={stage.name} className={cn(
                      "flex items-center justify-between p-4 rounded-lg border transition-all duration-300",
                      isCompleted ? "bg-green-500/5 border-green-500/20" :
                      isCurrent ? "bg-primary/5 border-primary/30 shadow-[0_0_15px_rgba(99,102,241,0.1)]" :
                      "bg-[#0f0f0f] border-[#1a1a1a] opacity-50"
                    )}>
                      <div className="flex items-center gap-4">
                        <div className={cn(
                          "w-6 h-6 rounded-full flex items-center justify-center",
                          isCompleted ? "bg-green-500 text-white" :
                          isCurrent ? "bg-primary text-white" :
                          "bg-muted text-muted-foreground"
                        )}>
                          {isCompleted ? <CheckCircle2 className="w-4 h-4" /> :
                           isCurrent ? <Loader2 className="w-4 h-4 animate-spin" /> :
                           <div className="w-1.5 h-1.5 bg-current rounded-full" />}
                        </div>
                        <span className={cn("font-semibold text-sm", isCurrent && "text-primary")}>{stage.name}</span>
                      </div>
                      {isCompleted && <span className="text-[10px] font-bold text-muted-foreground">{stage.duration}</span>}
                      {isCurrent && <span className="text-[10px] font-bold text-primary animate-pulse uppercase tracking-widest">Running</span>}
                    </div>
                  );
                })}
              </div>
            </div>

            {progress === 100 && (
              <Button className="w-full bg-primary hover:bg-primary/90 py-7 text-base font-bold uppercase tracking-widest animate-in zoom-in duration-500" onClick={() => navigate('/papers/1')}>
                View Results
                <ChevronRight className="w-5 h-5 ml-2" />
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
