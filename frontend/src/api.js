import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
});

// Unwrap successful responses and normalise errors into { data, error }.
const call = async (fn) => {
  try {
    const response = await fn();
    return { data: response.data, error: null };
  } catch (err) {
    const error = err.response?.data ?? err.message ?? 'Unknown error';
    return { data: null, error };
  }
};

// ── Auth ──────────────────────────────────────────────────────────────────

export const login = (username, password) =>
  call(() => api.post('/auth/login/', { username, password }));

export const logout = () =>
  call(() => api.post('/auth/logout/'));

export const getCurrentUser = () =>
  call(() => api.get('/auth/me/'));

// ── Tenants ───────────────────────────────────────────────────────────────

export const getTenants = () =>
  call(() => api.get('/tenants/'));

// ── Data Sources ──────────────────────────────────────────────────────────

export const getDataSources = (params = {}) =>
  call(() => api.get('/data-sources/', { params }));

export const getDataSource = (id) =>
  call(() => api.get(`/data-sources/${id}/`));

// ── Upload ────────────────────────────────────────────────────────────────

export const uploadCSV = (file, dataSourceId) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('data_source_id', dataSourceId);
  return call(() =>
    api.post('/ingestion/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  );
};

// ── Ingestion Batches ─────────────────────────────────────────────────────

export const getIngestionBatches = (params = {}) =>
  call(() => api.get('/ingestion-batches/', { params }));

export const getIngestionBatch = (id) =>
  call(() => api.get(`/ingestion-batches/${id}/`));

// ── Emission Records ──────────────────────────────────────────────────────

export const getEmissionRecords = (filters = {}) =>
  call(() => api.get('/emission-records/', { params: filters }));

export const getEmissionRecord = (id) =>
  call(() => api.get(`/emission-records/${id}/`));

export const updateEmissionRecord = (id, data) =>
  call(() => api.patch(`/emission-records/${id}/`, data));

export const bulkApproveRecords = (recordIds) =>
  call(() => api.post('/emission-records/bulk-approve/', { ids: recordIds }));

// ── Analytics ─────────────────────────────────────────────────────────────

export const getAnalyticsSummary = (params = {}) =>
  call(() => api.get('/analytics/summary/', { params }));

export default api;
