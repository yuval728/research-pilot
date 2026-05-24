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
      theme: 'base',
      securityLevel: 'loose',
      fontFamily: 'Inter',
      themeVariables: {
        darkMode: false,
        background: '#fcfcfb',
        primaryColor: '#f7f5f2',
        primaryTextColor: '#1f1f1f',
        primaryBorderColor: '#ddd8d2',
        lineColor: '#8a867f',
        secondaryColor: '#f1efec',
        tertiaryColor: '#f6f4f1',
      },
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
    <Card className="bg-gradient-to-br from-[#fcfcfb] via-[#f6f4f1] to-[#efeae4] text-[#1f1f1f] border border-[#e6e1da] shadow-[0_8px_22px_-18px_rgba(0,0,0,0.2)] p-4 flex items-center justify-center my-4 overflow-auto hide-scrollbar">
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
