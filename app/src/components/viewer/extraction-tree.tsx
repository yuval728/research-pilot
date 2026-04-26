import * as React from 'react';
import { useState } from 'react';
import { ChevronDown, ChevronRight, Database, BarChart3, Layers, Target, AlertCircle, Lightbulb, FileJson } from 'lucide-react';
import { ExtractionData } from '@/types';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Button } from '@/components/ui/button';

interface ExtractionTreeProps {
  data: ExtractionData;
}

export function ExtractionTree({ data }: ExtractionTreeProps) {
  const [showRaw, setShowRaw] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">Extracted Knowledge</h3>
        <Badge variant="outline" className="text-[10px] border-[#1a1a1a] text-muted-foreground">SCHEMA V1.2</Badge>
      </div>

      <div className="space-y-4">
        <Section title="Task & Problem" icon={Target} defaultOpen>
          <div className="space-y-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Primary Task</p>
              <p className="text-sm font-medium">{data.task}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Problem Statement</p>
              <p className="text-sm text-muted-foreground leading-relaxed">{data.problem_statement}</p>
            </div>
          </div>
        </Section>

        <Section title="Key Contributions" icon={Lightbulb}>
          <ul className="space-y-2">
            {data.key_contributions.map((c, i) => (
              <li key={i} className="flex gap-3 text-sm text-muted-foreground">
                <span className="text-primary font-bold">•</span>
                {c}
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Architecture" icon={Layers}>
          <div className="grid grid-cols-1 gap-3">
            {data.architecture_components.map((comp, i) => (
              <Card key={i} className="bg-secondary/30 border-[#1a1a1a] p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-primary truncate">{comp.name}</span>
                  <Badge variant="outline" className="text-[9px] h-4 px-1 border-primary/20 text-primary/80">{comp.type}</Badge>
                </div>
                <p className="text-[11px] text-muted-foreground leading-tight">{comp.description}</p>
              </Card>
            ))}
          </div>
        </Section>

        <Section title="Datasets" icon={Database}>
          <Table>
            <TableHeader>
              <TableRow className="border-[#1a1a1a] hover:bg-transparent">
                <TableHead className="text-[10px] font-bold h-8">Name</TableHead>
                <TableHead className="text-[10px] font-bold h-8">Size</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.datasets.map((ds, i) => (
                <TableRow key={i} className="border-[#1a1a1a] hover:bg-secondary/30">
                  <TableCell className="py-2 text-[11px] font-medium">{ds.name}</TableCell>
                  <TableCell className="py-2 text-[11px] text-muted-foreground">{ds.size}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>

        <Section title="Metrics & Results" icon={BarChart3}>
          <Table>
            <TableHeader>
              <TableRow className="border-[#1a1a1a] hover:bg-transparent">
                <TableHead className="text-[10px] font-bold h-8">Metric</TableHead>
                <TableHead className="text-[10px] font-bold h-8">Value</TableHead>
                <TableHead className="text-[10px] font-bold h-8">Delta</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.metrics_results.map((m, i) => (
                <TableRow key={i} className="border-[#1a1a1a] hover:bg-secondary/30">
                  <TableCell className="py-2 text-[11px] font-medium">{m.metric}</TableCell>
                  <TableCell className="py-2 text-[11px] text-primary font-bold">{m.value}</TableCell>
                  <TableCell className="py-2 text-[11px] text-green-500">{m.vs_baseline}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>

        <Section title="Limitations" icon={AlertCircle}>
          <ul className="space-y-2">
            {data.limitations.map((l, i) => (
              <li key={i} className="flex gap-3 text-sm text-muted-foreground">
                <span className="text-destructive font-bold">•</span>
                {l}
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <div className="pt-4">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-between text-muted-foreground hover:text-primary border border-[#1a1a1a] h-10"
          onClick={() => setShowRaw(!showRaw)}
        >
          <div className="flex items-center gap-2">
            <FileJson className="w-4 h-4" />
            <span className="text-[10px] font-bold uppercase tracking-widest">View Raw JSON</span>
          </div>
          {showRaw ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </Button>
        {showRaw && (
          <div className="mt-3 p-4 bg-[#050505] rounded-lg border border-[#1a1a1a] overflow-x-auto">
            <pre className="text-[10px] font-mono text-muted-foreground leading-relaxed">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, children, defaultOpen = false }: { title: string, icon: any, children: React.ReactNode, defaultOpen?: boolean }) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="border-b border-[#1a1a1a] pb-4 last:border-0">
      <CollapsibleTrigger className="flex items-center justify-between w-full group py-2">
        <div className="flex items-center gap-3">
          <div className={cn("p-1.5 rounded-md transition-colors", isOpen ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground group-hover:text-foreground")}>
            <Icon className="w-3.5 h-3.5" />
          </div>
          <span className={cn("text-xs font-bold uppercase tracking-widest transition-colors", isOpen ? "text-foreground" : "text-muted-foreground group-hover:text-foreground")}>
            {title}
          </span>
        </div>
        {isOpen ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-4 pl-11">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
