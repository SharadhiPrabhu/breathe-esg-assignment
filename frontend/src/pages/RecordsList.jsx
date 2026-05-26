import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search, SlidersHorizontal, Calendar, Download } from 'lucide-react';
import './RecordsList.css';
import { getEmissionRecords } from '../api';

const PAGE_SIZE = 25;

const SCOPE_LABELS = { 1: 'Scope 1', 2: 'Scope 2', 3: 'Scope 3' };

function ScopeBadge({ scope }) {
  return <span className={`badge badge-scope-${scope}`}>{SCOPE_LABELS[scope] ?? `Scope ${scope}`}</span>;
}

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status.replace('_', ' ')}</span>;
}

function QualityBadge({ score }) {
  return <span className={`badge badge-${score}`}>{score}</span>;
}

function Pagination({ page, totalPages, totalCount, onPage }) {
  if (totalPages <= 1) return null;
  const pages = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(totalPages, page + 2);
  for (let i = start; i <= end; i++) pages.push(i);

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderTop: '1px solid var(--border)', fontSize: 13 }}>
      <span style={{ color: 'var(--text-muted)' }}>
        {totalCount.toLocaleString()} records · page {page} of {totalPages}
      </span>
      <div style={{ display: 'flex', gap: 4 }}>
        <button className="btn btn-secondary" style={{ padding: '4px 10px' }} disabled={page === 1} onClick={() => onPage(page - 1)}>‹ Prev</button>
        {start > 1 && <><button className="btn btn-secondary" style={{ padding: '4px 10px' }} onClick={() => onPage(1)}>1</button><span style={{ padding: '4px 4px', color: 'var(--text-muted)' }}>…</span></>}
        {pages.map(p => (
          <button
            key={p}
            className={p === page ? 'btn btn-primary' : 'btn btn-secondary'}
            style={{ padding: '4px 10px' }}
            onClick={() => onPage(p)}
          >{p}</button>
        ))}
        {end < totalPages && <><span style={{ padding: '4px 4px', color: 'var(--text-muted)' }}>…</span><button className="btn btn-secondary" style={{ padding: '4px 10px' }} onClick={() => onPage(totalPages)}>{totalPages}</button></>}
        <button className="btn btn-secondary" style={{ padding: '4px 10px' }} disabled={page === totalPages} onClick={() => onPage(page + 1)}>Next ›</button>
      </div>
    </div>
  );
}

function RecordsList() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [records, setRecords]   = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);

  // Derive filter state from URL so the browser back button works
  const filters = {
    review_status:     searchParams.get('review_status') ?? '',
    ghg_scope:         searchParams.get('ghg_scope') ?? '',
    activity_date_from: searchParams.get('activity_date_from') ?? '',
    activity_date_to:   searchParams.get('activity_date_to') ?? '',
    search:            searchParams.get('search') ?? '',
  };
  const page = parseInt(searchParams.get('page') ?? '1', 10);

  const setFilter = (key, value) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value) next.set(key, value); else next.delete(key);
      next.delete('page'); // reset to page 1 on filter change
      return next;
    });
  };

  const setPage = (p) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set('page', String(p));
      return next;
    });
  };

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params = { page_size: PAGE_SIZE, page, ordering: '-activity_date' };
    if (filters.review_status)     params.review_status = filters.review_status;
    if (filters.ghg_scope)         params.ghg_scope = filters.ghg_scope;
    if (filters.activity_date_from) params.activity_date_from = filters.activity_date_from;
    if (filters.activity_date_to)   params.activity_date_to = filters.activity_date_to;
    if (filters.search)            params.search = filters.search;

    const { data, error: fetchError } = await getEmissionRecords(params);

    if (data) {
      setRecords(data.results ?? []);
      setTotalCount(data.count ?? 0);
    }
    if (fetchError) {
      setError(typeof fetchError === 'string' ? fetchError : 'Failed to load records.');
    }
    setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);
  const activeFilterCount = [filters.review_status, filters.ghg_scope, filters.activity_date_from, filters.activity_date_to, filters.search].filter(Boolean).length;

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Emission Records</h1>
          <p>Browse, filter, and review all normalized emission records</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {totalCount > 0 && !loading && (
            <span style={{ fontSize: 13, color: 'var(--text-muted)', paddingTop: 2 }}>
              {totalCount.toLocaleString()} records
            </span>
          )}
          <button
            className="btn btn-secondary"
            title="Export (UI only)"
            style={{ display: 'flex', alignItems: 'center', gap: 6 }}
            onClick={() => alert('Export not implemented in demo')}
          >
            <Download size={15} />
            Export
          </button>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header" style={{ padding: '10px 16px', fontSize: 13 }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <SlidersHorizontal size={14} />
            Filters
            {activeFilterCount > 0 && (
              <span className="badge badge-pending" style={{ fontSize: 10 }}>{activeFilterCount}</span>
            )}
          </span>
          {activeFilterCount > 0 && (
            <button className="btn btn-secondary" onClick={() => setSearchParams({})}
              style={{ fontSize: 12, padding: '3px 8px' }}>
              Clear all
            </button>
          )}
        </div>
        <div className="card-body" style={{ padding: '14px 16px' }}>
          <div className="filters-grid">

            <div>
              <label className="form-label" style={{ marginBottom: 4 }}>Search</label>
              <div className="input-icon-wrap">
                <span className="input-icon"><Search size={14} /></span>
                <input
                  className="form-control"
                  type="search"
                  placeholder="Activity type, location…"
                  value={filters.search}
                  onChange={(e) => setFilter('search', e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="form-label" style={{ marginBottom: 4 }}>Review Status</label>
              <select className="form-control" value={filters.review_status} onChange={(e) => setFilter('review_status', e.target.value)}>
                <option value="">All statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="needs_info">Needs Info</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>

            <div>
              <label className="form-label" style={{ marginBottom: 4 }}>GHG Scope</label>
              <select className="form-control" value={filters.ghg_scope} onChange={(e) => setFilter('ghg_scope', e.target.value)}>
                <option value="">All scopes</option>
                <option value="1">Scope 1</option>
                <option value="2">Scope 2</option>
                <option value="3">Scope 3</option>
              </select>
            </div>

            <div>
              <label className="form-label" style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                <Calendar size={13} /> Date from
              </label>
              <input className="form-control" type="date" value={filters.activity_date_from} onChange={(e) => setFilter('activity_date_from', e.target.value)} />
            </div>

            <div>
              <label className="form-label" style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
                <Calendar size={13} /> Date to
              </label>
              <input className="form-control" type="date" value={filters.activity_date_to} onChange={(e) => setFilter('activity_date_to', e.target.value)} />
            </div>

          </div>
        </div>
      </div>

      {/* ── Table ── */}
      <div className="card">
        {loading ? (
          <div className="loading">Loading records…</div>
        ) : error ? (
          <div className="card-body">
            <div className="alert alert-error">{error}</div>
          </div>
        ) : records.length === 0 ? (
          <div className="card-body">
            <div className="empty-state">
              <p>{activeFilterCount > 0 ? 'No records match the current filters.' : 'No emission records found.'}</p>
              {activeFilterCount > 0 && (
                <button className="btn btn-secondary" onClick={() => setSearchParams({})}>Clear filters</button>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Activity Type</th>
                    <th>Scope</th>
                    <th>Location</th>
                    <th>Quantity</th>
                    <th>CO2e</th>
                    <th>Quality</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.id} onClick={() => navigate(`/records/${record.id}`)}>
                      <td style={{ whiteSpace: 'nowrap' }}>{record.activity_date}</td>
                      <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {record.activity_type}
                      </td>
                      <td><ScopeBadge scope={record.ghg_scope} /></td>
                      <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-muted)' }}>
                        {record.location_name ?? record.country_code ?? '—'}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {parseFloat(record.quantity_normalized).toFixed(2)} {record.unit_normalized}
                      </td>
                      <td style={{ whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
                        {parseFloat(record.co2e_kg).toFixed(2)} kg
                      </td>
                      <td><QualityBadge score={record.data_quality_score} /></td>
                      <td><StatusBadge status={record.review_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} totalPages={totalPages} totalCount={totalCount} onPage={setPage} />
          </>
        )}
      </div>
    </div>
  );
}

export default RecordsList;
