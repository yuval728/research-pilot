import { PipelineRun } from '@/types';

const API_URL = import.meta.env.VITE_API_URL || '';

export const pipelineApi = {
  async triggerRun(paperId: string): Promise<{ run_id: string }> {
    const response = await fetch(`${API_URL}/pipeline/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_id: paperId }),
    });
    if (!response.ok) throw new Error('Failed to trigger pipeline');
    return response.json();
  },

  async getRunStatus(runId: string): Promise<PipelineRun> {
    const response = await fetch(`${API_URL}/pipeline/runs/${runId}`);
    if (!response.ok) throw new Error('Failed to fetch run status');
    return response.json();
  },

  async retryStage(runId: string, stageName: string): Promise<void> {
    const response = await fetch(`${API_URL}/pipeline/runs/${runId}/retry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage_name: stageName }),
    });
    if (!response.ok) throw new Error('Failed to retry stage');
  }
};
