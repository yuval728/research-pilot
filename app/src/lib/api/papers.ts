import { Paper, OutputBundle } from '@/types';
import { API_BASE_URL } from '../config';
import { apiFetch, getAccessToken } from './http';

function ensureApi() {
  if (!API_BASE_URL) throw new Error('VITE_API_URL must be set to call the backend API');
}

export const papersApi = {
  async listPapers(filters?: any): Promise<Paper[]> {
    ensureApi();
    return apiFetch(`/v1/papers`);
  },

  async getPaper(id: string): Promise<Paper> {
    ensureApi();
    return apiFetch(`/v1/papers/${id}`);
  },

  async uploadPaper(file: File): Promise<Paper> {
    ensureApi();
    const url = `/v1/papers/upload`;
    const token = (await getAccessToken()) ?? null;
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE_URL}${url}`, { method: 'POST', headers, body: formData });
    if (!res.ok) throw new Error('Failed to upload paper');
    return res.json();
  },

  async createFromArxiv(url: string): Promise<Paper> {
    ensureApi();
    return apiFetch(`/v1/papers/arxiv`, { method: 'POST', json: { url } });
  },

  async getOutputBundle(id: string): Promise<OutputBundle> {
    ensureApi();
    return apiFetch(`/v1/papers/${id}/outputs`);
  },

  async getReportMarkdown(id: string): Promise<string> {
    ensureApi();
    return apiFetch(`/v1/papers/${id}/outputs/report.md`);
  },

  async getCodeSource(id: string): Promise<string> {
    ensureApi();
    return apiFetch(`/v1/papers/${id}/outputs/code.py`);
  },

  async getNotebook(id: string): Promise<Blob> {
    ensureApi();
    const token = (await getAccessToken()) ?? null;
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await fetch(`${API_BASE_URL}/api/v1/papers/${id}/outputs/notebook.ipynb`, { headers });
    if (!response.ok) throw new Error('Failed to download notebook');
    return response.blob();
  },
};
