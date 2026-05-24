import { useEffect, useMemo, useState } from 'react';
import { BookOpen, Filter, Globe, Layers3 } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { PaperCard } from '@/components/library/paper-card';
import { SearchBar } from '@/components/library/search-bar';
import { papersApi } from '@/lib/api/papers';
import { useAuth } from '@/lib/hooks/use-auth';
import { Paper, PaperListItem } from '@/types';
import { toast } from 'sonner';

const SORT_OPTIONS = ['Newest', 'Oldest', 'Title A-Z', 'Title Z-A'] as const;
type SortOption = (typeof SORT_OPTIONS)[number];

export default function ExplorePage() {
  const { user } = useAuth();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [paperItems, setPaperItems] = useState<PaperListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeDomain, setActiveDomain] = useState('All Domains');
  const [activeSubdomain, setActiveSubdomain] = useState('All Subdomains');
  const [sortBy, setSortBy] = useState<SortOption>('Newest');

  useEffect(() => {
    const fetchPublicPapers = async () => {
      try {
        const data = await papersApi.listPublicPapers();
        setPaperItems(data);
        setPapers(data.map((item) => item.paper));
      } catch (error) {
        console.error('Failed to fetch public papers:', error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchPublicPapers();
  }, []);

  const handleSearch = (query: string) => {
    setSearchQuery(query);
  };

  const allPapers = papers.filter((p) => p.metadata);

  const domainOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of allPapers) {
      if (p.metadata?.domain?.trim()) set.add(p.metadata.domain.trim());
    }
    return ['All Domains', ...Array.from(set).sort((a, b) => a.localeCompare(b))];
  }, [allPapers]);

  const subdomainOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of allPapers) {
      const md = p.metadata;
      if (!md?.sub_domain?.trim()) continue;
      if (activeDomain !== 'All Domains' && md.domain !== activeDomain) continue;
      set.add(md.sub_domain.trim());
    }
    return ['All Subdomains', ...Array.from(set).sort((a, b) => a.localeCompare(b))];
  }, [allPapers, activeDomain]);

  useEffect(() => {
    if (!subdomainOptions.includes(activeSubdomain)) {
      setActiveSubdomain('All Subdomains');
    }
  }, [activeSubdomain, subdomainOptions]);

  const displayPapers = papers
    .filter((p) => {
      if (!p.metadata) return false;
      if (activeDomain !== 'All Domains' && p.metadata.domain !== activeDomain) {
        return false;
      }
      if (activeSubdomain !== 'All Subdomains' && p.metadata.sub_domain !== activeSubdomain) {
        return false;
      }
      if (searchQuery.trim()) {
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

  const handleImport = (_paperId: string) => {
    toast.success('Imported to your library');
  };

  return (
    <div className="flex flex-col min-h-screen">
      <Header title="Explore">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
          <Globe className="w-4 h-4" />
          Public library
        </div>
      </Header>

      <div className="p-8 max-w-6xl mx-auto w-full space-y-8">
        <SearchBar
          onSearch={handleSearch}
          placeholder="Search public papers by title or author..."
          helperText="Local filter across public papers"
        />

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
          <div className="relative lg:col-span-1">
            <Layers3 className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <select
              value={activeDomain}
              onChange={(e) => {
                setActiveDomain(e.target.value);
                setActiveSubdomain('All Subdomains');
              }}
              className="h-10 w-full rounded-lg border border-border bg-card pl-9 pr-8 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
              aria-label="Filter by domain"
            >
              {domainOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div className="relative lg:col-span-1">
            <Layers3 className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <select
              value={activeSubdomain}
              onChange={(e) => setActiveSubdomain(e.target.value)}
              className="h-10 w-full rounded-lg border border-border bg-card pl-9 pr-8 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
              aria-label="Filter by subdomain"
              disabled={subdomainOptions.length <= 1}
            >
              {subdomainOptions.map((option) => (
                <option key={option} value={option}>{option}</option>
              ))}
            </select>
          </div>

          <div className="relative lg:col-span-1 lg:col-start-4">
            <Filter className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="h-10 w-full rounded-lg border border-border bg-card pl-9 pr-8 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
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
        ) : !isEmpty ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {displayPapers.map((paper) => (
              <PaperCard
                key={paper.id}
                paper={paper}
                pipelineRun={latestRunByPaperId[paper.id] ?? null}
                onImport={paper.user_id && paper.user_id === user?.id ? undefined : handleImport}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-20 text-center space-y-4">
            <div className="w-16 h-16 bg-secondary rounded-full flex items-center justify-center text-muted-foreground">
              <BookOpen className="w-8 h-8" />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-semibold">No public papers found</h3>
              <p className="text-sm text-muted-foreground max-w-xs">
                Try adjusting your filters or search terms.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
