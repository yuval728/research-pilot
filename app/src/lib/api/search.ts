import { Paper } from '@/types';
import { API_BASE_URL } from '../config';
import { apiFetch } from './http';

function ensureApi() {
  if (!API_BASE_URL) throw new Error('VITE_API_URL must be set to call the backend API');
}

export interface SearchResult {
  paper: Paper;
  score: number;
}

export const searchApi = {
  async searchPapers(query: string, limit: number = 10): Promise<SearchResult[]> {
    ensureApi();
    return apiFetch(`/v1/search?q=${encodeURIComponent(query)}&limit=${limit}`);
  },

  async getSimilarPapers(paperId: string): Promise<Paper[]> {
    ensureApi();
    return apiFetch(`/v1/papers/${paperId}/similar`);
  },
};
