import { Link, useLocation } from 'react-router-dom';
import { BookOpen, Plus, LogOut, User } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useAuth } from '@/lib/hooks/use-auth';
import { useEffect, useState } from 'react';
import { papersApi } from '@/lib/api/papers';

export function Sidebar() {
  const location = useLocation();
  const { user, signOut } = useAuth();
  const [paperCount, setPaperCount] = useState<number | null>(null);

  // Fetch real paper count for the usage widget
  useEffect(() => {
    papersApi
      .listPapers()
      .then((papers) => setPaperCount(papers.length))
      .catch(() => setPaperCount(null));
  }, []);

  const navItems = [
    { name: 'Library', icon: BookOpen, path: '/library' },
    { name: 'Add Paper', icon: Plus, path: '/ingest' },
  ];

  // Derive a display name from email (part before @)
  const displayName = user?.email
    ? user.email.split('@')[0]
    : 'User';

  return (
    <div className="w-60 bg-[#0f0f0f] border-r border-[#1a1a1a] flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-primary rounded flex items-center justify-center text-white font-bold">
          RP
        </div>
        <div className="flex flex-col">
          <span className="font-semibold text-sm tracking-tight">Research Pilot</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={cn(
              'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
              location.pathname === item.path
                ? 'bg-primary/10 text-primary'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary',
            )}
          >
            <item.icon className="w-4 h-4" />
            {item.name}
          </Link>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 space-y-4">
        {/* Usage widget — real count */}
        <div className="bg-secondary/50 rounded-lg p-3 border border-border/50">
          <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-wider mb-1">
            Library
          </p>
          <p className="text-xs font-medium">
            {paperCount === null ? '…' : `${paperCount} paper${paperCount !== 1 ? 's' : ''}`}
          </p>
          {paperCount !== null && paperCount > 0 && (
            <div className="w-full bg-muted h-1 rounded-full mt-2 overflow-hidden">
              {/* Visual fill — capped at 30 papers for the bar */}
              <div
                className="bg-primary h-full transition-all duration-500"
                style={{ width: `${Math.min((paperCount / 30) * 100, 100)}%` }}
              />
            </div>
          )}
        </div>

        <Separator className="bg-[#1a1a1a]" />

        {/* User info */}
        <div className="flex items-center gap-3 px-2">
          <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center text-muted-foreground">
            <User className="w-4 h-4" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{displayName}</p>
            <p className="text-[10px] text-muted-foreground truncate">{user?.email}</p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive"
            onClick={signOut}
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
