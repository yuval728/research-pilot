import { useState, useEffect, useCallback } from 'react';
import { Plus, BookOpen, Filter } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { SearchBar } from '@/components/library/search-bar';
import { PaperCard } from '@/components/library/paper-card';
import { papersApi } from '@/lib/api/papers';
import { searchApi } from '@/lib/api/search';
import { Paper, PaperListItem } from '@/types';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const DOMAINS = ['All', 'NLP', 'Computer Vision', 'Reinforcement Learning', 'Generative'];
const SORT_OPTIONS = ['Newest', 'Oldest', 'Title A-Z', 'Title Z-A'] as const;
type SortOption = (typeof SORT_OPTIONS)[number];

export default function LibraryPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [paperItems, setPaperItems] = useState<PaperListItem[]>([]);
  const [searchResults, setSearchResults] = useState<Paper[] | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSearching, setIsSearching] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeDomain, setActiveDomain] = useState('All');
  const [sortBy, setSortBy] = useState<SortOption>('Newest');
  const navigate = useNavigate();

  useEffect(() => {
    const fetchPapers = async () => {
      try {
        const data = await papersApi.listPapers();
        setPaperItems(data);
        setPapers(data.map((item) => item.paper));
      } catch (error) {
        console.error('Failed to fetch papers:', error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchPapers();
  }, []);

  const handleSearch = useCallback(async (query: string) => {
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
      setSearchResults(null);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const baseList = searchResults !== null ? searchResults : papers;

  const displayPapers = baseList
    .filter((p) => {
      if (!p.metadata) return false;
      if (activeDomain !== 'All') {
        const selected = activeDomain.toLowerCase();
        const d = p.metadata.domain?.toLowerCase() ?? '';
        const sd = p.metadata.sub_domain?.toLowerCase() ?? '';
        if (!d.includes(selected) && !sd.includes(selected)) return false;
      }

      if (searchResults === null && searchQuery.trim().length > 2) {
        const q = searchQuery.toLowerCase();
        return (
          p.metadata.title.toLowerCase().includes(q) ||
          p.metadata.authors.some((a) => a.toLowerCase().includes(q))
        );
      }
      return true;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'Oldest':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
        case 'Title A-Z':
          return (a.metadata?.title ?? '').localeCompare(b.metadata?.title ?? '');
        case 'Title Z-A':
          return (b.metadata?.title ?? '').localeCompare(a.metadata?.title ?? '');
        case 'Newest':
        default:
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

  const isEmpty = !isLoading && displayPapers.length === 0;
  const latestRunByPaperId = Object.fromEntries(
    paperItems.map((item) => [item.paper.id, item.latest_run]),
  );

  return (
    <div className="flex flex-col min-h-screen">
      <Header title="Library">
        <Button size="sm" className="bg-primary hover:bg-primary/90" onClick={() => navigate('/ingest')}>
          <Plus className="w-4 h-4 mr-2" />
          Add Paper
        </Button>
      </Header>

      <div className="p-8 max-w-6xl mx-auto w-full space-y-8">
        <SearchBar onSearch={handleSearch} isSearching={isSearching} />

        <div className="flex items-center justify-between gap-4">
          <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar">
            {DOMAINS.map((domain) => (
              <Badge
                key={domain}
                variant="secondary"
                onClick={() => setActiveDomain(domain)}
                className={cn(
                  'px-4 py-1.5 cursor-pointer transition-colors border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70',
                  activeDomain === domain
                    ? 'bg-primary text-white border-primary'
                    : 'bg-secondary/70 text-foreground/80 hover:bg-secondary hover:text-foreground',
                )}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setActiveDomain(domain);
                  }
                }}
              >
                {domain}
              </Badge>
            ))}
          </div>

          <div className="relative">
            <Filter className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="h-9 rounded-md border border-border bg-card pl-9 pr-8 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
              aria-label="Sort papers"
            >
              {SORT_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  Sort: {option}
                </option>
              ))}
            </select>
          </div>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-48 bg-secondary/30 rounded-xl animate-pulse border border-border" />
            ))}
          </div>
        ) : isSearching ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[1, 2].map((i) => (
              <div key={i} className="h-48 bg-secondary/30 rounded-xl animate-pulse border border-border" />
            ))}
          </div>
        ) : !isEmpty ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {displayPapers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} pipelineRun={latestRunByPaperId[paper.id] ?? null} />
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
