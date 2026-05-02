import { PipelineRun } from '@/types';
import { API_BASE_URL } from '../config';
import { apiFetch } from './http';

function ensureApi() {
  if (!API_BASE_URL) throw new Error('VITE_API_URL must be set to call the backend API');
}

export const pipelineApi = {
  async triggerRun(paperId: string): Promise<{ run_id: string }> {
    ensureApi();
    return apiFetch(`/v1/pipeline/run/${paperId}`, { method: 'POST', json: { paper_id: paperId } });
  },

  async getRunStatus(runId: string): Promise<PipelineRun> {
    ensureApi();
    return apiFetch(`/v1/pipeline/runs/${runId}`);
  },

  async retryStage(runId: string, stageName: string): Promise<void> {
    ensureApi();
    await apiFetch(`/v1/pipeline/runs/${runId}/stages/${stageName}/retry`, { method: 'POST', json: { stage_name: stageName } });
  },
};
