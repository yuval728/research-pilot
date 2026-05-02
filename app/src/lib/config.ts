export const RAW_API_URL = import.meta.env.VITE_API_URL || '';
export const API_BASE_URL = RAW_API_URL || 'http://localhost:8000';
export const POLLING_INTERVAL_MS = Number(import.meta.env.VITE_POLLING_INTERVAL_MS) || 3000;

export const FEATURE_FLAGS = {
  useSSE: import.meta.env.VITE_USE_SSE === 'true' || false,
};
