import { PipelineRun } from '@/types';
import { apiFetch } from './http';

function ensureApi() {
  if (!import.meta.env.VITE_API_URL && !window.location.hostname) {
    throw new Error('VITE_API_URL must be set to call the backend API');
  }
}

export const pipelineApi = {
  /**
   * Trigger a pipeline run for a paper.
   * POST /api/v1/pipeline/run/{paper_id}  — paper_id is a path param, no body needed.
   * Returns the PipelineRun record (status=pending immediately).
   */
  async triggerRun(paperId: string): Promise<PipelineRun> {
    return apiFetch(`/api/v1/pipeline/run/${paperId}`, { method: 'POST' });
  },

  /**
   * Get full status + stage results for a run.
   * GET /api/v1/pipeline/runs/{run_id}
   */
  async getRunStatus(runId: string): Promise<PipelineRun> {
    return apiFetch(`/api/v1/pipeline/runs/${runId}`);
  },

  async getLatestRunForPaper(paperId: string): Promise<PipelineRun | null> {
    return apiFetch(`/api/v1/pipeline/papers/${paperId}/latest-run`);
  },

  /**
   * Retry a single failed stage.
   * POST /api/v1/pipeline/runs/{run_id}/stages/{stage_name}/retry
   */
  async retryStage(runId: string, stageName: string): Promise<void> {
    await apiFetch(`/api/v1/pipeline/runs/${runId}/stages/${stageName}/retry`, {
      method: 'POST',
    });
  },

  /**
   * Get the latest pipeline run for a given paper.
   * We poll GET /api/v1/pipeline/runs/{run_id} — but to look up by paper we need
   * to first find the run. This helper fetches the paper's run list from the backend.
   * For now we query the run status by run_id (stored after trigger).
   *
   * If you want runs-by-paper, add a query param filter once the backend supports it.
   */
  async getRunForPaper(_paperId: string): Promise<PipelineRun | null> {
    // Backend doesn't expose a list-runs-by-paper endpoint yet.
    // Callers should store runId after triggerRun and use getRunStatus.
    return null;
  },
};
