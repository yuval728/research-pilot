import { useState } from 'react';
import { Search, X, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface SearchBarProps {
  onSearch: (query: string) => void;
  className?: string;
  /** Shows a spinner while semantic search is in flight */
  isSearching?: boolean;
  placeholder?: string;
  helperText?: string;
}

export function SearchBar({
  onSearch,
  className,
  isSearching = false,
  placeholder = 'Search papers by concept, method, architecture...',
  helperText = 'Use natural language to find relevant papers in your library.',
}: SearchBarProps) {
  const [query, setQuery] = useState('');

  const handleClear = () => {
    setQuery('');
    onSearch('');
  };

  return (
    <div className={cn('space-y-2', className)}>
      <div className="relative group rounded-xl border border-border bg-card/60 backdrop-blur-sm transition-colors focus-within:border-primary/70">
        {isSearching ? (
          <Loader2 className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-primary animate-spin" />
        ) : (
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
        )}

        <Input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            onSearch(e.target.value);
          }}
          placeholder={placeholder}
          className="h-14 border-0 bg-transparent pl-11 pr-12 text-lg text-foreground placeholder:text-muted-foreground/80 focus-visible:ring-0"
        />

        {query && (
          <button
            onClick={handleClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-1.5 hover:bg-secondary rounded-md text-muted-foreground"
            aria-label="Clear search"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-[0.14em]">
        {isSearching ? 'Searching...' : helperText}
      </p>
    </div>
  );
}
