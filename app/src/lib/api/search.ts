import { Paper } from '@/types';

const API_URL = import.meta.env.VITE_API_URL || '';

export interface SearchResult {
  paper: Paper;
  score: number;
}

export const searchApi = {
  async searchPapers(query: string, limit: number = 10): Promise<SearchResult[]> {
    const response = await fetch(`${API_URL}/search?q=${encodeURIComponent(query)}&limit=${limit}`);
    if (!response.ok) throw new Error('Search failed');
    return response.json();
  },

  async getSimilarPapers(paperId: string): Promise<Paper[]> {
    const response = await fetch(`${API_URL}/papers/${paperId}/similar`);
    if (!response.ok) throw new Error('Failed to fetch similar papers');
    return response.json();
  }
};
