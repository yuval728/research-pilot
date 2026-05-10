import { useState, useEffect } from 'react';
import mermaid from 'mermaid';
import { ZoomIn, ZoomOut, Maximize2, Code, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { DiagramOutput } from '@/types';

const TYPE_LABELS: Record<string, string> = {
  architecture: 'Architecture',
  training_flow: 'Training Flow',
  inference_flow: 'Inference Flow',
};

interface DiagramViewerProps {
  diagrams: DiagramOutput[];
}

export function DiagramViewer({ diagrams }: DiagramViewerProps) {
  const [activeType, setActiveType] = useState<string>(
    diagrams[0]?.diagram_type ?? 'architecture',
  );
  const [svg, setSvg] = useState<string>('');
  const [renderError, setRenderError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [showSource, setShowSource] = useState(false);

  const activeDiagram = diagrams.find((d) => d.diagram_type === activeType) ?? diagrams[0];

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'neutral',
      securityLevel: 'loose',
      fontFamily: 'Inter',
      // themeVariables: {
      //   darkMode: false,
      //   background: '#ffffff',
      //   primaryColor: '#1a1a1a',
      //   primaryTextColor: '#fff',
      //   primaryBorderColor: '#333',
      //   lineColor: '#666',
      //   secondaryColor: '#2a2a2a',
      //   tertiaryColor: '#3a3a3a',
      // }
    });
  }, []);

  useEffect(() => {
    if (!activeDiagram?.dsl_code) return;
    setRenderError(null);

    const renderDiagram = async () => {
      const id = `mermaid-${activeDiagram.diagram_type}-${Date.now()}`;
      try {
        const { svg: rendered } = await mermaid.render(id, activeDiagram.dsl_code);
        setSvg(rendered);
      } catch (error: any) {
        console.error('Mermaid render error:', error);
        setRenderError('Failed to render diagram. The DSL may contain unsupported syntax.');
        setSvg('');

        // Mermaid injects a temporary div into the document body to calculate SVG bounds.
        // On error, it fails to clean this up, leaving a "Syntax error" SVG bomb in the UI.
        const errorElement = document.getElementById('d' + id);
        if (errorElement) {
          errorElement.remove();
        }
      }
    };

    renderDiagram();
  }, [activeDiagram]);

  if (!diagrams.length) {
    return (
      <p className="text-muted-foreground text-sm">No diagrams available for this paper.</p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Diagram type switcher */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {diagrams.map((d) => (
            <Button
              key={d.diagram_type}
              variant={d.diagram_type === activeType ? 'default' : 'outline'}
              size="sm"
              onClick={() => {
                setActiveType(d.diagram_type);
                setZoom(1);
              }}
              className={cn(
                'h-8 text-[10px] font-bold uppercase tracking-widest border-[#1a1a1a]',
                d.diagram_type === activeType
                  ? 'bg-primary'
                  : 'text-muted-foreground hover:bg-secondary',
              )}
            >
              {TYPE_LABELS[d.diagram_type] ?? d.diagram_type.replace('_', ' ')}
            </Button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 border-[#1a1a1a]"
            onClick={() => setZoom((z) => Math.min(z + 0.2, 3))}
          >
            <ZoomIn className="w-4 h-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 border-[#1a1a1a]"
            onClick={() => setZoom((z) => Math.max(z - 0.2, 0.3))}
          >
            <ZoomOut className="w-4 h-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 border-[#1a1a1a]"
            onClick={() => setZoom(1)}
          >
            <Maximize2 className="w-4 h-4" />
          </Button>
          <Separator orientation="vertical" className="h-4 bg-[#1a1a1a]" />
        </div>
      </div>

      {/* Diagram canvas */}
      <Card className="bg-[#050505] border-[#1a1a1a] p-8 flex items-center justify-center min-h-[500px] relative overflow-auto hide-scrollbar">
        {renderError ? (
          <p className="text-destructive text-sm">{renderError}</p>
        ) : svg ? (
          <div
            className="transition-transform duration-200 ease-out mermaid flex items-center justify-center"
            style={{ transform: `scale(${zoom})`, transformOrigin: 'center center' }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        ) : (
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        )}
      </Card>

      {/* Collapsible DSL source */}
      <Collapsible
        open={showSource}
        onOpenChange={setShowSource}
        className="border border-[#1a1a1a] rounded-lg overflow-hidden"
      >
        <CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-3 bg-[#0f0f0f] hover:bg-secondary transition-colors">
          <div className="flex items-center gap-2">
            <Code className="w-4 h-4 text-muted-foreground" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              View Mermaid Source
            </span>
          </div>
          <ChevronDown
            className={cn(
              'w-4 h-4 text-muted-foreground transition-transform',
              showSource && 'rotate-180',
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="p-4 bg-[#050505] font-mono text-xs text-muted-foreground leading-relaxed border-t border-[#1a1a1a]">
            <pre>{activeDiagram?.dsl_code}</pre>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
