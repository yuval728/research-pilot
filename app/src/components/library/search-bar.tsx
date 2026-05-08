import { useState } from 'react';
import { Search, X, Loader2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface SearchBarProps {
  onSearch: (query: string) => void;
  className?: string;
  /** Shows a spinner while semantic search is in flight */
  isSearching?: boolean;
}

export function SearchBar({ onSearch, className, isSearching = false }: SearchBarProps) {
  const [query, setQuery] = useState('');

  const handleClear = () => {
    setQuery('');
    onSearch('');
  };

  return (
    <div className={cn('relative group', className)}>
      {isSearching ? (
        <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-primary animate-spin" />
      ) : (
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
      )}
      <Input
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          onSearch(e.target.value);
        }}
        placeholder="Search papers by concept, method, architecture..."
        className="pl-10 pr-10 py-6 bg-[#0f0f0f] border-[#1a1a1a] focus:border-primary focus:ring-0 transition-all text-base"
      />
      {query && (
        <button
          onClick={handleClear}
          className="absolute right-3 top-1/2 -translate-y-1/2 p-1 hover:bg-secondary rounded-md text-muted-foreground"
        >
          <X className="w-4 h-4" />
        </button>
      )}
      <p className="mt-2 text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
        {isSearching ? 'Searching…' : 'Semantic search powered by Gemini embeddings'}
      </p>
    </div>
  );
}
