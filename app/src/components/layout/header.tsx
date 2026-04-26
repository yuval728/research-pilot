import * as React from 'react';
import { cn } from '@/lib/utils';

interface HeaderProps {
  title: string;
  children?: React.ReactNode;
  className?: string;
}

export function Header({ title, children, className }: HeaderProps) {
  return (
    <header className={cn("h-16 border-b border-[#1a1a1a] flex items-center justify-between px-8 bg-background/50 backdrop-blur-md sticky top-0 z-10", className)}>
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      <div className="flex items-center gap-4">
        {children}
      </div>
    </header>
  );
}
