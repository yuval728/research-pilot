import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Download, FileText, Code2, GitBranch, Layout, Clock, CheckCircle2 } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ExtractionTree } from '@/components/viewer/extraction-tree';
import { SummaryTabs } from '@/components/viewer/summary-tabs';
import { DiagramViewer } from '@/components/viewer/diagram-viewer';
import { CodeViewer } from '@/components/viewer/code-viewer';
import { papersApi } from '@/lib/api/papers';
import { Paper, OutputBundle } from '@/types';
import { cn } from '@/lib/utils';
import Markdown from 'react-markdown';

export default function PaperViewerPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [bundle, setBundle] = useState<OutputBundle | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      try {
        const [paperData, bundleData] = await Promise.all([
          papersApi.getPaper(id),
          papersApi.getOutputBundle(id)
        ]);
        setPaper(paperData);
        setBundle(bundleData);
      } catch (error) {
        console.error(error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchData();
  }, [id]);

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

  if (!paper || !bundle) return <div>Paper not found</div>;

  return (
    <div className="flex flex-col min-h-screen">
      <header className="border-b border-[#1a1a1a] bg-background/50 backdrop-blur-md sticky top-0 z-20">
        <div className="px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground" onClick={() => navigate('/library')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Library
            </Button>
            <div className="space-y-1">
              <h1 className="text-xl font-bold tracking-tight">{paper.metadata.title}</h1>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span>{paper.metadata.authors.join(', ')}</span>
                <span>•</span>
                <span>{paper.metadata.venue} {paper.metadata.year}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant="secondary" className="bg-primary/10 text-primary border-none font-bold uppercase tracking-widest text-[10px]">
              {paper.metadata.sub_domain}
            </Badge>
            <div className="flex items-center gap-1 bg-green-500/10 text-green-500 px-2 py-1 rounded-full text-[9px] font-black uppercase tracking-tighter">
              <CheckCircle2 className="w-3 h-3" />
              COMPLETED
            </div>
          </div>
        </div>
        <div className="px-8 pb-4 flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <Download className="w-3.5 h-3.5 mr-2" />
            Report (MD)
          </Button>
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <Download className="w-3.5 h-3.5 mr-2" />
            Code (.PY)
          </Button>
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <Download className="w-3.5 h-3.5 mr-2" />
            Notebook (.IPYNB)
          </Button>
        </div>
      </header>

      <div className="flex-1 flex gap-8 p-8 max-w-[1600px] mx-auto w-full overflow-hidden">
        {/* Main Content */}
        <div className="flex-[0.65] min-w-0">
          <Tabs defaultValue="summary" className="w-full">
            <TabsList className="bg-transparent border-b border-[#1a1a1a] w-full justify-start rounded-none h-12 p-0 gap-8">
              <TabsTrigger value="summary" className="data-[state=active]:border-primary data-[state=active]:text-primary border-b-2 border-transparent rounded-none bg-transparent px-0 font-bold text-[10px] uppercase tracking-[0.2em]">
                Summary
              </TabsTrigger>
              <TabsTrigger value="diagrams" className="data-[state=active]:border-primary data-[state=active]:text-primary border-b-2 border-transparent rounded-none bg-transparent px-0 font-bold text-[10px] uppercase tracking-[0.2em]">
                Diagrams
              </TabsTrigger>
              <TabsTrigger value="code" className="data-[state=active]:border-primary data-[state=active]:text-primary border-b-2 border-transparent rounded-none bg-transparent px-0 font-bold text-[10px] uppercase tracking-[0.2em]">
                Code
              </TabsTrigger>
              <TabsTrigger value="report" className="data-[state=active]:border-primary data-[state=active]:text-primary border-b-2 border-transparent rounded-none bg-transparent px-0 font-bold text-[10px] uppercase tracking-[0.2em]">
                Full Report
              </TabsTrigger>
            </TabsList>

            <div className="py-8">
              <TabsContent value="summary" className="mt-0">
                <SummaryTabs summaries={bundle.summaries} />
              </TabsContent>
              <TabsContent value="diagrams" className="mt-0">
                <DiagramViewer dsl={bundle.diagrams[0].dsl_code} type="ARCHITECTURE" />
              </TabsContent>
              <TabsContent value="code" className="mt-0">
                <CodeViewer code={mockCode} syntheticData={bundle.code?.synthetic_data_description || ''} />
              </TabsContent>
              <TabsContent value="report" className="mt-0">
                <div className="prose prose-invert max-w-none markdown-body">
                  <Markdown>{mockReport}</Markdown>
                </div>
              </TabsContent>
            </div>
          </Tabs>
        </div>

        {/* Sidebar */}
        <div className="flex-[0.35] min-w-[320px]">
          <div className="bg-[#0f0f0f] border border-[#1a1a1a] rounded-xl p-6 sticky top-40 h-[calc(100vh-12rem)] overflow-y-auto custom-scrollbar">
            {bundle.extraction && <ExtractionTree data={bundle.extraction} />}
          </div>
        </div>
      </div>

      {/* Pipeline Timeline */}
      <div className="px-8 py-6 border-t border-[#1a1a1a] bg-[#050505]">
        <div className="flex items-center justify-between mb-4">
          <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Pipeline Execution Timeline</h4>
          <div className="flex gap-4 text-[10px] font-bold text-muted-foreground">
            <span className="flex items-center gap-1"><CheckCircle2 className="w-3 h-3 text-green-500" /> Completed</span>
            <span className="flex items-center gap-1"><Clock className="w-3 h-3 text-blue-500" /> Cached</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {['Ingest', 'Classify', 'Extract', 'Summarize', 'Embed', 'Diagram', 'Code', 'Report'].map((stage, i) => (
            <div key={stage} className="flex-1 flex flex-col gap-2">
              <div className={cn("h-1 rounded-full", i < 4 ? "bg-green-500" : i < 6 ? "bg-blue-500" : "bg-green-500")} />
              <div className="flex items-center justify-between px-1">
                <span className="text-[9px] font-bold uppercase tracking-tighter text-muted-foreground">{stage}</span>
                <span className="text-[9px] font-medium text-muted-foreground/50">{i === 4 || i === 5 ? 'CACHED' : '2.4s'}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const mockCode = `import torch
import torch.nn as nn

class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, num_heads):
        super(MultiHeadAttention, self).__init__()
        assert d_model % num_heads == 0

        self.d_model = d_model
        self.num_heads = num_heads
        self.d_k = d_model // num_heads

        self.W_q = nn.Linear(d_model, d_model)
        self.W_k = nn.Linear(d_model, d_model)
        self.W_v = nn.Linear(d_model, d_model)
        self.W_o = nn.Linear(d_model, d_model)

    def scaled_dot_product_attention(self, Q, K, V, mask=None):
        attn_scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.d_k)
        if mask is not None:
            attn_scores = attn_scores.masked_fill(mask == 0, -1e9)
        attn_probs = torch.softmax(attn_scores, dim=-1)
        output = torch.matmul(attn_probs, V)
        return output, attn_probs

    def forward(self, Q, K, V, mask=None):
        # Implementation of multi-head attention...
        pass`;

const mockReport = `
# Analysis Report: Attention Is All You Need

## Executive Summary
The Transformer architecture represents a paradigm shift in sequence modeling, moving away from recurrent and convolutional layers in favor of a pure attention-based mechanism. This allows for significantly more parallelization during training and has led to state-of-the-art performance in machine translation tasks.

## Key Findings
1. **Self-Attention Efficiency**: The self-attention mechanism reduces the path length between any two positions in a sequence to a constant O(1), facilitating the learning of long-range dependencies.
2. **Parallelization**: Unlike RNNs, which require sequential processing, Transformers allow for parallel computation across the entire sequence length.
3. **Multi-Head Attention**: By using multiple attention heads, the model can simultaneously focus on different aspects of the input (e.g., syntactic vs. semantic relationships).

## Architecture Deep Dive
The model consists of an encoder and a decoder, each composed of a stack of identical layers. Each layer has two sub-layers: a multi-head self-attention mechanism and a simple, position-wise fully connected feed-forward network.

### Encoder
The encoder maps an input sequence of symbol representations to a sequence of continuous representations.

### Decoder
The decoder generates an output sequence of symbols one element at a time, using the encoder's output and previously generated symbols.
`;
