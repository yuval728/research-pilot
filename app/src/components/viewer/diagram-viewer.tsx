import { useState, useEffect } from 'react';
import mermaid from 'mermaid';
import { ZoomIn, ZoomOut, Maximize2, RefreshCw, Code } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';

interface DiagramViewerProps {
  dsl: string;
  type: string;
}

export function DiagramViewer({ dsl, type }: DiagramViewerProps) {
  const [svg, setSvg] = useState<string>('');
  const [zoom, setZoom] = useState(1);
  const [showSource, setShowSource] = useState(false);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
      fontFamily: 'Inter',
    });

    const renderDiagram = async () => {
      try {
        const { svg } = await mermaid.render(`mermaid-${type}`, dsl);
        setSvg(svg);
      } catch (error) {
        console.error('Mermaid render error:', error);
      }
    };

    renderDiagram();
  }, [dsl, type]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {['ARCHITECTURE', 'TRAINING_FLOW', 'INFERENCE_FLOW'].map((t) => (
            <Button
              key={t}
              variant={t === type ? 'default' : 'outline'}
              size="sm"
              className={cn(
                "h-8 text-[10px] font-bold uppercase tracking-widest border-[#1a1a1a]",
                t === type ? "bg-primary" : "text-muted-foreground hover:bg-secondary"
              )}
            >
              {t.replace('_', ' ')}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" className="h-8 w-8 border-[#1a1a1a]" onClick={() => setZoom(z => Math.min(z + 0.2, 2))}>
            <ZoomIn className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8 border-[#1a1a1a]" onClick={() => setZoom(z => Math.max(z - 0.2, 0.5))}>
            <ZoomOut className="w-4 h-4" />
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8 border-[#1a1a1a]" onClick={() => setZoom(1)}>
            <Maximize2 className="w-4 h-4" />
          </Button>
          <Separator orientation="vertical" className="h-4 bg-[#1a1a1a]" />
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <RefreshCw className="w-3.5 h-3.5 mr-2" />
            Regenerate
          </Button>
        </div>
      </div>

      <Card className="bg-[#050505] border-[#1a1a1a] p-8 flex items-center justify-center min-h-[400px] relative overflow-hidden">
        <div
          className="transition-transform duration-200 ease-out"
          style={{ transform: `scale(${zoom})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </Card>

      <Collapsible open={showSource} onOpenChange={setShowSource} className="border border-[#1a1a1a] rounded-lg overflow-hidden">
        <CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-3 bg-[#0f0f0f] hover:bg-secondary transition-colors">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-muted-foreground" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">View Mermaid Source</span>
          </div>
          <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", showSource && "rotate-180")} />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="p-4 bg-[#050505] font-mono text-xs text-muted-foreground leading-relaxed border-t border-[#1a1a1a]">
            <pre>{dsl}</pre>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

function cn(...classes: any[]) {
  return classes.filter(Boolean).join(' ');
}

import { Separator } from '@/components/ui/separator';
import { ChevronDown } from 'lucide-react';
