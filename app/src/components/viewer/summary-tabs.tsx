import { useState } from 'react';
import Markdown from 'react-markdown';
import { cn } from '@/lib/utils';
import { SummaryOutput } from '@/types';
import { motion, AnimatePresence } from 'motion/react';

interface SummaryTabsProps {
  summaries: SummaryOutput[];
}

// Backend emits lowercase level values
const LEVEL_CONFIG: { id: SummaryOutput['level']; label: string }[] = [
  { id: 'paragraph', label: 'Paragraph' },
  { id: 'section_by_section', label: 'Sections' },
  { id: 'bullets', label: 'Bullets' },
  { id: 'eli5', label: 'ELI5' },
];

export function SummaryTabs({ summaries }: SummaryTabsProps) {
  // Default to the first available summary level
  const defaultLevel = summaries[0]?.level ?? 'paragraph';
  const [activeLevel, setActiveLevel] = useState<SummaryOutput['level']>(defaultLevel);

  const activeSummary =
    summaries.find((s) => s.level === activeLevel) ?? summaries[0];

  // Only show tabs for levels that have content
  const availableLevels = LEVEL_CONFIG.filter((l) =>
    summaries.some((s) => s.level === l.id),
  );

  if (!activeSummary) {
    return <p className="text-muted-foreground text-sm">No summaries available.</p>;
  }

  return (
    <div className="space-y-8">
      {availableLevels.length > 1 && (
        <div className="flex p-1 bg-[#0f0f0f] border border-[#1a1a1a] rounded-lg w-fit">
          {availableLevels.map((level) => (
            <button
              key={level.id}
              onClick={() => setActiveLevel(level.id)}
              className={cn(
                'px-6 py-2 text-[10px] font-bold uppercase tracking-widest rounded-md transition-all relative',
                activeLevel === level.id
                  ? 'text-white'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {activeLevel === level.id && (
                <motion.div
                  layoutId="active-tab"
                  className="absolute inset-0 bg-primary rounded-md"
                  transition={{ type: 'spring', bounce: 0.2, duration: 0.6 }}
                />
              )}
              <span className="relative z-10">{level.label}</span>
            </button>
          ))}
        </div>
      )}

      <AnimatePresence mode="wait">
        <motion.div
          key={activeLevel}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.2 }}
          className="prose prose-invert max-w-none"
        >
          <div className="markdown-body text-muted-foreground leading-relaxed text-base">
            <Markdown>{activeSummary.content}</Markdown>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
