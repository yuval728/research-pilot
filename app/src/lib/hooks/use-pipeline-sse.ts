import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../config';
import { getAccessToken } from '../api/http';
import { PipelineRun } from '@/types';

/**
 * Connects to the SSE stream for a pipeline run.
 * Backend: GET /api/v1/pipeline/runs/{run_id}/stream
 * Emits PipelineRun-shaped payloads via data: {...}\n\n
 *
 * Note: EventSource doesn't support custom headers. We include the token
 * in the query string for the initial handshake; the backend reads it from
 * the Authorization query param as a fallback.
 */
export function usePipelineSSE(runId: string | null) {
  const [run, setRun] = useState<Partial<PipelineRun> | null>(null);
  const [connected, setConnected] = useState(false);
  const [done, setDone] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId || !API_BASE_URL) return;

    setDone(false);

    const connect = async () => {
      // EventSource cannot set headers; append token as query param so the
      // backend can optionally validate it via a middleware.
      const token = await getAccessToken();
      const qs = token ? `?token=${encodeURIComponent(token)}` : '';
      const url = `${API_BASE_URL}/api/v1/pipeline/runs/${runId}/stream${qs}`;

      const es = new EventSource(url);
      esRef.current = es;
      setConnected(true);

      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as Partial<PipelineRun>;
          setRun(data);
          const s = data.status;
          if (s === 'completed' || s === 'failed' || s === 'partial') {
            setDone(true);
            es.close();
            setConnected(false);
          }
        } catch {
          // ignore parse errors
        }
      };

      es.onerror = () => {
        setConnected(false);
        es.close();
      };
    };

    connect();

    return () => {
      esRef.current?.close();
      setConnected(false);
    };
  }, [runId]);

  return { run, connected, done };
}
