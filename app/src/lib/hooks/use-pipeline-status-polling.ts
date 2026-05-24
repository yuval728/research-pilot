import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '../api/http';
import { POLLING_INTERVAL_MS } from '../config';

type RunStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | string;

export function usePipelineStatus(runId: string | null) {
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    if (!runId) return;
    stoppedRef.current = false;

    let interval = POLLING_INTERVAL_MS;

    const poll = async () => {
      try {
        const data = await apiFetch(`/v1/pipeline/runs/${runId}`);
        const s = data?.status as RunStatus;
        setStatus(s ?? null);
        if (s === 'SUCCESS' || s === 'FAILED' || s === 'CANCELLED') {
          stoppedRef.current = true;
        }
      } catch (e: any) {
        setError(e?.message || 'Unknown error');
        // exponential backoff on errors
        interval = Math.min(30000, interval * 2);
      }
    };

    // initial poll immediately
    poll();
    const timer = setInterval(() => {
      if (stoppedRef.current) return;
      poll();
    }, interval);

    return () => {
      stoppedRef.current = true;
      clearInterval(timer);
    };
  }, [runId]);

  return { status, error };
}
