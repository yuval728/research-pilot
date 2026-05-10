import { useState, useEffect } from 'react';
import mermaid from 'mermaid';
import { Card } from '@/components/ui/card';

interface MarkdownDiagramProps {
  code: string;
}

export function MarkdownDiagram({ code }: MarkdownDiagramProps) {
  const [svg, setSvg] = useState<string>('');
  const [renderError, setRenderError] = useState<string | null>(null);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
      fontFamily: 'Inter',
      themeVariables: {
        darkMode: true,
        background: '#050505',
        primaryColor: '#1a1a1a',
        primaryTextColor: '#fff',
        primaryBorderColor: '#333',
        lineColor: '#666',
        secondaryColor: '#2a2a2a',
        tertiaryColor: '#3a3a3a',
      }
    });
  }, []);

  useEffect(() => {
    if (!code) return;
    setRenderError(null);

    const renderDiagram = async () => {
      const id = `mermaid-md-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
      try {
        const { svg: rendered } = await mermaid.render(id, code);
        setSvg(rendered);
      } catch (error: any) {
        console.error('Mermaid render error in markdown:', error);
        setRenderError('Failed to render diagram.');
        setSvg('');
        const errorElement = document.getElementById('d' + id);
        if (errorElement) errorElement.remove();
      }
    };

    renderDiagram();
  }, [code]);

  return (
    <Card className="bg-[#050505] border-[#1a1a1a] p-4 flex items-center justify-center my-4 overflow-auto hide-scrollbar">
      {renderError ? (
        <p className="text-destructive text-sm font-mono">{renderError}</p>
      ) : svg ? (
        <div
          className="mermaid flex items-center justify-center"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      )}
    </Card>
  );
}
