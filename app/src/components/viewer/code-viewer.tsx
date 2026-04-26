import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { vscodeDark } from '@uiw/codemirror-theme-vscode';
import { Download, FileCode, Database, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { ChevronDown } from 'lucide-react';

interface CodeViewerProps {
  code: string;
  syntheticData: string;
}

export function CodeViewer({ code, syntheticData }: CodeViewerProps) {
  const [showData, setShowData] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-md">
            <FileCode className="w-4 h-4 text-primary" />
          </div>
          <div>
            <h3 className="text-sm font-bold tracking-tight">implementation.py</h3>
            <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest">Python 3.10 • PyTorch</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <Download className="w-3.5 h-3.5 mr-2" />
            .py
          </Button>
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <Download className="w-3.5 h-3.5 mr-2" />
            .ipynb
          </Button>
          <Button variant="outline" size="sm" className="h-8 border-[#1a1a1a] text-[10px] font-bold uppercase tracking-widest">
            <RefreshCw className="w-3.5 h-3.5 mr-2" />
            Regenerate
          </Button>
        </div>
      </div>

      <Card className="border-[#1a1a1a] overflow-hidden rounded-xl">
        <CodeMirror
          value={code}
          height="500px"
          theme={vscodeDark}
          extensions={[python()]}
          editable={false}
          className="text-sm"
        />
      </Card>

      <Collapsible open={showData} onOpenChange={setShowData} className="border border-[#1a1a1a] rounded-lg overflow-hidden">
        <CollapsibleTrigger className="flex items-center justify-between w-full px-4 py-3 bg-[#0f0f0f] hover:bg-secondary transition-colors">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-muted-foreground" />
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Synthetic Data Description</span>
          </div>
          <ChevronDown className={cn("w-4 h-4 text-muted-foreground transition-transform", showData && "rotate-180")} />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="p-6 bg-[#050505] text-sm text-muted-foreground leading-relaxed border-t border-[#1a1a1a]">
            {syntheticData}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
