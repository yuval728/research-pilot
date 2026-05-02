import { useEffect, useState } from 'react';
import { API_BASE_URL, RAW_API_URL } from '../config';

export function usePipelineSSE(runId: string | null) {
  const [lastEvent, setLastEvent] = useState<any>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!runId || !RAW_API_URL) return;
    const url = `${API_BASE_URL}/v1/pipeline/runs/${runId}/stream`;
    const es = new EventSource(url);
    setConnected(true);

    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        setLastEvent(data);
      } catch (e) {
        setLastEvent(ev.data);
      }
    };
    es.onerror = () => {
      setConnected(false);
      es.close();
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [runId]);

  return { lastEvent, connected };
}
