import { describe, expect, it } from 'vitest';
import { hasBundleOutputs, resolveViewerRunStatus, shouldStreamRun, toDisplayStatus } from '../src/lib/pipeline-status';
import { OutputBundle, PipelineRun } from '../src/types';

function makeBundle(overrides: Partial<OutputBundle> = {}): OutputBundle {
  return {
    paper_id: 'paper-1',
    summaries: [],
    diagrams: [],
    code: null,
    report: null,
    extraction: null,
    ...overrides,
  };
}

function makeRun(overrides: Partial<PipelineRun> = {}): PipelineRun {
  return {
    id: 'run-1',
    paper_id: 'paper-1',
    status: 'pending',
    stages: {},
    started_at: null,
    completed_at: null,
    total_tokens: null,
    error: null,
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

describe('pipeline status helpers', () => {
  it('treats empty bundle with no run as pending, not completed', () => {
    const bundle = makeBundle();
    expect(resolveViewerRunStatus(null, bundle)).toBe('pending');
    expect(toDisplayStatus(null, bundle)).toBe('PENDING');
  });

  it('treats existing outputs as completed without a run', () => {
    const bundle = makeBundle({
      report: {
        paper_id: 'paper-1',
        markdown_path: 'outputs/paper-1/report.md',
      },
    });
    expect(hasBundleOutputs(bundle)).toBe(true);
    expect(resolveViewerRunStatus(null, bundle)).toBe('completed');
    expect(toDisplayStatus(null, bundle)).toBe('COMPLETED');
  });

  it('streams only active runs with ids', () => {
    expect(shouldStreamRun(makeRun({ status: 'pending' }))).toBe(true);
    expect(shouldStreamRun(makeRun({ status: 'running' }))).toBe(true);
    expect(shouldStreamRun(makeRun({ status: 'completed' }))).toBe(false);
    expect(shouldStreamRun({ status: 'running' } as Partial<PipelineRun>)).toBe(false);
  });

  it('maps partial runs to completed display state', () => {
    expect(toDisplayStatus(makeRun({ status: 'partial' }))).toBe('COMPLETED');
  });
});
