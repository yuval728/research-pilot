import { useEffect, useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { vscodeDark } from '@uiw/codemirror-theme-vscode';
import { ChevronDown, Database, Download, FileCode, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { papersApi } from '@/lib/api/papers';
import { cn } from '@/lib/utils';

interface CodeViewerProps {
  paperId: string;
  pythonPath: string | null;
  syntheticData: string;
}

function downloadText(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

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

export function CodeViewer({ paperId, pythonPath, syntheticData }: CodeViewerProps) {
  const [code, setCode] = useState('');
  const [isFetching, setIsFetching] = useState(true);
  const [showData, setShowData] = useState(false);
  const [downloading, setDownloading] = useState<'py' | 'ipynb' | null>(null);

  useEffect(() => {
    if (!pythonPath) {
      setCode('# Code source not available yet.');
      setIsFetching(false);
      return;
    }

    const fetchSource = async () => {
      setIsFetching(true);
      try {
        const src = await papersApi.getCodeSource(paperId);
        setCode(src);
      } catch {
        setCode('# Code source not available yet.');
      } finally {
        setIsFetching(false);
      }
    };
    fetchSource();
  }, [paperId, pythonPath]);

  const handleDownloadPy = async () => {
    setDownloading('py');
    try {
      downloadText(code, `${paperId}_implementation.py`, 'text/x-python');
    } catch {
      toast.error('Failed to download .py file');
    } finally {
      setDownloading(null);
    }
  };

  // const handleDownloadNotebook = async () => {
  //   setDownloading('ipynb');
  //   try {
  //     const blob = await papersApi.getNotebook(paperId);
  //     downloadBlob(blob, `${paperId}_notebook.ipynb`);
  //   } catch {
  //     toast.error('Failed to download notebook');
  //   } finally {
  //     setDownloading(null);
  //   }
  // };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-md">
            <FileCode className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-bold tracking-tight">implementation.py</h3>
            <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest">
              Python 3.10 · PyTorch
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest"
            onClick={handleDownloadPy}
            disabled={!pythonPath || !code || downloading === 'py'}
          >
            {downloading === 'py' ? (
              <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5 mr-2" />
            )}
            .py
          </Button>
          {/* <Button
            variant="outline"
            size="sm"
            className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest"
            onClick={handleDownloadNotebook}
            disabled={downloading === 'ipynb'}
          >
            {downloading === 'ipynb' ? (
              <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5 mr-2" />
            )}
            .ipynb
          </Button> */}
        </div>
      </div>

      <Card className="border-[#1a1a1a] overflow-hidden rounded-xl">
        {isFetching ? (
          <div className="h-[500px] flex items-center justify-center bg-[#1e1e1e]">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <CodeMirror
            value={code}
            height="500px"
            theme={vscodeDark}
            extensions={[python()]}
            editable={false}
            className="text-sm"
          />
        )}
      </Card>

      <Collapsible
        open={showData}
        onOpenChange={setShowData}
        className="border border-[#1a1a1a] rounded-lg overflow-hidden"
      >
        <CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-3 bg-[#0f0f0f] hover:bg-secondary transition-colors">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-muted-foreground" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Synthetic Data Description
            </span>
          </div>
          <ChevronDown
            className={cn(
              'w-4 h-4 text-muted-foreground transition-transform',
              showData && 'rotate-180',
            )}
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="p-6 bg-[#050505] text-sm text-muted-foreground leading-relaxed border-t border-[#1a1a1a]">
            {syntheticData || 'No synthetic data description available.'}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
