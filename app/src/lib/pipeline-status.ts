import { OutputBundle, PipelineRun } from '@/types';

export type ViewerRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial';
export type DisplayStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';

function hasOutputs(bundle: OutputBundle | null | undefined): boolean {
  if (!bundle) return false;
  return Boolean(
    bundle.summaries.length > 0 ||
    bundle.diagrams.length > 0 ||
    bundle.report ||
    bundle.code ||
    bundle.extraction,
  );
}

export function resolveViewerRunStatus(
  run: Partial<PipelineRun> | null | undefined,
  bundle: OutputBundle | null | undefined,
): ViewerRunStatus {
  if (run?.status) return run.status;
  if (hasOutputs(bundle)) return 'completed';
  return 'pending';
}

export function shouldStreamRun(run: Partial<PipelineRun> | null | undefined): boolean {
  return Boolean(run?.id && (run.status === 'pending' || run.status === 'running'));
}

export function hasBundleOutputs(bundle: OutputBundle | null | undefined): boolean {
  return hasOutputs(bundle);
}

export function toDisplayStatus(
  run: PipelineRun | null | undefined,
  bundle?: OutputBundle | null,
): DisplayStatus {
  const status = resolveViewerRunStatus(run, bundle);
  switch (status) {
    case 'running':
      return 'RUNNING';
    case 'completed':
    case 'partial':
      return 'COMPLETED';
    case 'failed':
      return 'FAILED';
    default:
      return 'PENDING';
  }
}
