import { Paper } from '@/types';
import { apiFetch } from './http';
import { API_BASE_URL } from '../config';

function ensureApi() {
  if (!API_BASE_URL) throw new Error('VITE_API_URL must be set to call the backend API');
}

export interface SearchResult {
  paper: Paper;
  score: number;
}

export const searchApi = {
  /**
   * Semantic search — backend expects POST /api/v1/search with JSON body.
   */
  async searchPapers(query: string, limit: number = 10): Promise<Paper[]> {
    ensureApi();
    // Backend route: POST /api/v1/search → returns list[Paper]
    return apiFetch(`/api/v1/search`, {
      method: 'POST',
      json: { query, limit },
    });
  },

  /**
   * Find papers similar to the given paper.
   * Backend route: GET /api/v1/search/similar/{paper_id}
   */
  async getSimilarPapers(paperId: string, limit: number = 5): Promise<Paper[]> {
    ensureApi();
    return apiFetch(`/api/v1/search/similar/${paperId}?limit=${limit}`);
  },
};
