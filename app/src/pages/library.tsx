import { useState, useEffect } from 'react';
import { Plus, BookOpen, Filter } from 'lucide-react';
import { Header } from '@/components/layout/header';
import { Button } from '@/components/ui/button';
import { SearchBar } from '@/components/library/search-bar';
import { PaperCard } from '@/components/library/paper-card';
import { papersApi } from '@/lib/api/papers';
import { Paper } from '@/types';
import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';

export default function LibraryPage() {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    const fetchPapers = async () => {
      try {
        const data = await papersApi.listPapers();
        setPapers(data);
      } catch (error) {
        console.error(error);
      } finally {
        setIsLoading(false);
      }
    };
    fetchPapers();
  }, []);

  const filteredPapers = papers.filter(p =>
    p.metadata.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    p.metadata.authors.some(a => a.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const domains = ['All', 'NLP', 'Computer Vision', 'Reinforcement Learning', 'Generative'];

  return (
    <div className="flex flex-col min-h-screen">
      <Header title="Library">
        <Button size="sm" className="bg-primary hover:bg-primary/90" onClick={() => navigate('/ingest')}>
          <Plus className="w-4 h-4 mr-2" />
          Add Paper
        </Button>
      </Header>

      <div className="p-8 max-w-6xl mx-auto w-full space-y-8">
        <SearchBar onSearch={setSearchQuery} />

        <div className="flex items-center justify-between">
          <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar">
            {domains.map((domain) => (
              <Badge
                key={domain}
                variant="secondary"
                className={cn(
                  "px-4 py-1.5 cursor-pointer transition-colors border-[#1a1a1a]",
                  domain === 'All' ? "bg-primary text-white border-primary" : "bg-secondary/50 text-muted-foreground hover:bg-secondary"
                )}
              >
                {domain}
              </Badge>
            ))}
          </div>
          <Button variant="outline" size="sm" className="border-[#1a1a1a] text-muted-foreground">
            <Filter className="w-3.5 h-3.5 mr-2" />
            Sort: Newest
          </Button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-48 bg-secondary/30 rounded-xl animate-pulse border border-[#1a1a1a]" />
            ))}
          </div>
        ) : filteredPapers.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {filteredPapers.map((paper) => (
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
                {searchQuery ? `No results for "${searchQuery}". Try a different search term.` : "Add your first paper to get started with AI-powered intelligence."}
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

function cn(...classes: any[]) {
  return classes.filter(Boolean).join(' ');
}
