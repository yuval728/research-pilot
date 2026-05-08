import { useState, useEffect, useCallback } from 'react';
import { Plus, BookOpen, Filter } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { SearchBar } from '@/components/library/search-bar';
import { PaperCard } from '@/components/library/paper-card';
import { papersApi } from '@/lib/api/papers';
import { searchApi } from '@/lib/api/search';
import { Paper } from '@/types';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const DOMAINS = ['All', 'NLP', 'Computer Vision', 'Reinforcement Learning', 'Generative'];

export default function LibraryPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [searchResults, setSearchResults] = useState<Paper[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeDomain, setActiveDomain] = useState('All');
  const navigate = useNavigate();

  // ── Fetch full library on mount ──────────────────────────────────────────
  useEffect(() => {
    const fetchPapers = async () => {
      try {
        const data = await papersApi.listPapers();
        setPapers(data);
      } catch (error) {
        console.error('Failed to fetch papers:', error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchPapers();
  }, []);

  // ── Semantic search via backend when query is long enough ────────────────
  const handleSearch = useCallback(
    async (query: string) => {
      setSearchQuery(query);

      if (query.trim().length <= 2) {
        setSearchResults(null);
        return;
      }

      setIsSearching(true);
      try {
        const results = await searchApi.searchPapers(query, 20);
        setSearchResults(results);
      } catch (err) {
        console.error('Search failed:', err);
        // Fall back to client-side filter
        setSearchResults(null);
      } finally {
        setIsSearching(false);
      }
    },
    [],
  );

  // ── Compute display list ─────────────────────────────────────────────────
  // If we have backend search results, use those; otherwise filter locally.
  const baseList = searchResults !== null ? searchResults : papers;

  const displayPapers = baseList.filter((p) => {
    if (!p.metadata) return false;
    if (activeDomain !== 'All') {
      const d = p.metadata.domain?.toLowerCase() ?? '';
      const sd = p.metadata.sub_domain?.toLowerCase() ?? '';
      if (!d.includes(activeDomain.toLowerCase()) && !sd.includes(activeDomain.toLowerCase()))
        return false;
    }
    // If we fell back to local filter (no backend results), also text-filter
    if (searchResults === null && searchQuery.trim().length > 2) {
      const q = searchQuery.toLowerCase();
      return (
        p.metadata.title.toLowerCase().includes(q) ||
        p.metadata.authors.some((a) => a.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const isEmpty = !isLoading && displayPapers.length === 0;

  return (
    <div className="flex flex-col min-h-screen">
      <Header title="Library">
        <Button
          size="sm"
          className="bg-primary hover:bg-primary/90"
          onClick={() => navigate('/ingest')}
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Paper
        </Button>
      </Header>

      <div className="p-8 max-w-6xl mx-auto w-full space-y-8">
        <SearchBar onSearch={handleSearch} isSearching={isSearching} />

        <div className="flex items-center justify-between">
          <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar">
            {DOMAINS.map((domain) => (
              <Badge
                key={domain}
                variant="secondary"
                onClick={() => setActiveDomain(domain)}
                className={cn(
                  'px-4 py-1.5 cursor-pointer transition-colors border-[#1a1a1a]',
                  activeDomain === domain
                    ? 'bg-primary text-white border-primary'
                    : 'bg-secondary/50 text-muted-foreground hover:bg-secondary',
                )}
              >
                {domain}
              </Badge>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            className="border-[#1a1a1a] text-muted-foreground"
          >
            <Filter className="w-3.5 h-3.5 mr-2" />
            Sort: Newest
          </Button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-48 bg-secondary/30 rounded-xl animate-pulse border border-[#1a1a1a]"
              />
            ))}
          </div>
        ) : isSearching ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[1, 2].map((i) => (
              <div
                key={i}
                className="h-48 bg-secondary/30 rounded-xl animate-pulse border border-[#1a1a1a]"
              />
            ))}
          </div>
        ) : !isEmpty ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {displayPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
            <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center text-muted-foreground">
              <BookOpen className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-semibold">No papers found</h3>
              <p className="text-sm text-muted-foreground max-w-xs">
                {searchQuery
                  ? `No results for "${searchQuery}". Try a different search term.`
                  : 'Add your first paper to get started with AI-powered intelligence.'}
              </p>
            </div>
            {!searchQuery && (
              <Button className="bg-primary" onClick={() => navigate('/ingest')}>
                Add Paper
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
