import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import LoginPage from '@/pages/login';
import LibraryPage from '@/pages/library';
import IngestPage from '@/pages/ingest';
import PaperViewerPage from '@/pages/paper-viewer';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route element={<DashboardLayout />}>
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/ingest" element={<IngestPage />} />
              <Route path="/papers/:id" element={<PaperViewerPage />} />
              <Route path="/" element={<Navigate to="/library" replace />} />
            </Route>

            <Route path="*" element={<Navigate to="/library" replace />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" theme="dark" closeButton />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
