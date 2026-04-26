import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { StageResult, PipelineRun } from '@/types';

export function usePipelineRealtime(runId: string | null) {
  const [stages, setStages] = useState<Record<string, StageResult>>({});
  const [runStatus, setRunStatus] = useState<PipelineRun['status']>('PENDING');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;

    // Initial fetch
    const fetchInitial = async () => {
      const { data: run } = await supabase
        .from('pipeline_runs')
        .select('*')
        .eq('id', runId)
        .single();

      if (run) {
        setRunStatus(run.status);
        setStages(run.stages || {});
      }
    };

    fetchInitial();

    // Realtime subscription
    const channel = supabase
      .channel(`pipeline:${runId}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'pipeline_runs',
          filter: `id=eq.${runId}`,
        },
        (payload) => {
          const updatedRun = payload.new as PipelineRun;
          setRunStatus(updatedRun.status);
          setStages(updatedRun.stages);
          if (updatedRun.error) setError(updatedRun.error);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [runId]);

  return { stages, runStatus, error };
}
