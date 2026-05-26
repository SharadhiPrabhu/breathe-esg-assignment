import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { Globe, FileText, Clock, CheckCircle } from 'lucide-react';
import { getEmissionRecords, getIngestionBatches } from '../api';
import { useTheme } from '../context/ThemeContext';
import './Dashboard.css';

const SCOPE_PALETTE = { 1: '#ef4444', 2: '#f59e0b', 3: '#3b82f6' };
const SCOPE_LABELS  = { 1: 'Scope 1', 2: 'Scope 2', 3: 'Scope 3' };

function formatCO2e(kg) {
  if (kg === null || kg === undefined) return '—';
  const num = parseFloat(kg);
  return num >= 1000 ? `${(num / 1000).toFixed(2)} t` : `${num.toFixed(2)} kg`;
}

// ── Skeleton loader ───────────────────────────────────────────────────────────
function SkeletonLoader() {
  return (
    <div>
      <div className="skeleton-header">
        <div className="skeleton-line" style={{ width: 180, height: 28 }} />
        <div className="skeleton-line" style={{ width: 260, height: 16, marginTop: 10 }} />
      </div>
      <div className="stat-grid">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="skeleton-card">
            <div className="skeleton-line" style={{ width: '30%', height: 11, marginBottom: 14 }} />
            <div className="skeleton-line" style={{ width: '60%', height: 36 }} />
            <div className="skeleton-line" style={{ width: '45%', height: 10, marginTop: 10 }} />
          </div>
        ))}
      </div>
      <div className="skeleton-card" style={{ height: 300, marginBottom: 24 }} />
      <div className="skeleton-card" style={{ height: 220 }} />
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, unit, accent }) {
  return (
    <div className="stat-card" style={{ '--accent': accent }}>
      <div className="stat-card-top">
        <span className="stat-label">{label}</span>
        <span className="stat-icon">{icon}</span>
      </div>
      <div className="stat-value">{value ?? '—'}</div>
      {unit && <div className="stat-unit">{unit}</div>}
    </div>
  );
}

// ── Scope chart ───────────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const bar = payload[0];
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label" style={{ color: bar.fill }}>{label}</div>
      <div className="chart-tooltip-value">{bar.value.toFixed(3)} t CO2e</div>
    </div>
  );
}

function ScopeChart({ bars, totalRecords }) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const hasData = bars.some(b => b.co2e > 0);
  const totalCO2e = bars.reduce((s, b) => s + b.co2e, 0);

  const gridColor     = isDark ? '#3a3a3a' : '#f0f0f0';
  const tickColor     = isDark ? '#9ca3af' : '#6b7280';
  const tickSecondary = isDark ? '#6b7280' : '#9ca3af';
  const cursorFill    = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      <div className="card-header">
        <span>Emissions by GHG Scope</span>
        <span className="chart-subtitle">
          Total: {totalCO2e.toFixed(2)} t CO2e · {totalRecords} records
        </span>
      </div>
      <div className="card-body" style={{ paddingTop: 8 }}>
        {!hasData ? (
          <div className="empty-state" style={{ padding: '32px 0' }}>
            <p>No emissions data to chart yet.</p>
            <Link to="/upload" className="btn btn-primary">Upload CSV data</Link>
          </div>
        ) : (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={bars} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis
                  dataKey="name"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: tickColor, fontSize: 13, fontWeight: 500 }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: tickSecondary, fontSize: 11 }}
                  tickFormatter={v => v === 0 ? '0' : `${v}t`}
                  width={36}
                />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: cursorFill }} />
                <Bar dataKey="co2e" radius={[4, 4, 0, 0]} maxBarSize={72}>
                  {bars.map(b => <Cell key={b.scope} fill={SCOPE_PALETTE[b.scope]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="scope-legend">
              {bars.map(b => (
                <span key={b.scope} className="scope-legend-item">
                  <span className="scope-legend-dot" style={{ background: SCOPE_PALETTE[b.scope] }} />
                  {b.name}
                  <strong>{b.co2e.toFixed(3)} t</strong>
                  {totalCO2e > 0 && (
                    <span className="scope-legend-pct">
                      {Math.round((b.co2e / totalCO2e) * 100)}%
                    </span>
                  )}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Badge components ──────────────────────────────────────────────────────────
function ScopeBadge({ scope }) {
  return <span className={`badge badge-scope-${scope}`}>{SCOPE_LABELS[scope] ?? `Scope ${scope}`}</span>;
}
function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status.replace('_', ' ')}</span>;
}
function QualityBadge({ score }) {
  return <span className={`badge badge-${score}`}>{score}</span>;
}

// ── Main component ────────────────────────────────────────────────────────────
function Dashboard() {
  const navigate = useNavigate();
  const [records,   setRecords]   = useState([]);
  const [batches,   setBatches]   = useState([]);
  const [stats,     setStats]     = useState(null);
  const [scopeBars, setScopeBars] = useState([]);
  const [loading,   setLoading]   = useState(true);
  const [error,     setError]     = useState(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      setLoading(true);
      setError(null);

      const [recordsResult, batchesResult] = await Promise.all([
        getEmissionRecords({ page_size: 50, ordering: '-activity_date' }),
        getIngestionBatches({ page_size: 5, ordering: '-uploaded_at' }),
      ]);

      if (cancelled) return;

      if (recordsResult.error && batchesResult.error) {
        setError(
          typeof recordsResult.error === 'string'
            ? recordsResult.error
            : 'Failed to load dashboard data. Is the backend running?'
        );
        setLoading(false);
        return;
      }

      const allRows    = recordsResult.data?.results ?? [];
      const totalCount = recordsResult.data?.count   ?? allRows.length;

      const totalCO2eKg = allRows.reduce((s, r) => s + parseFloat(r.co2e_kg || 0), 0);
      const pending     = allRows.filter(r => r.review_status === 'pending').length;
      const highQ       = allRows.filter(r => r.data_quality_score === 'high').length;
      const qualityPct  = allRows.length ? Math.round((highQ / allRows.length) * 100) : null;

      const bars = [1, 2, 3].map(scope => ({
        name: `Scope ${scope}`,
        scope,
        co2e: allRows
          .filter(r => r.ghg_scope === scope)
          .reduce((s, r) => s + parseFloat(r.co2e_kg || 0), 0) / 1000,
      }));

      setRecords(allRows.slice(0, 10));
      setBatches(batchesResult.data?.results ?? []);
      setStats({ totalCO2eKg, totalRecords: totalCount, pendingReviews: pending, highQualityPct: qualityPct });
      setScopeBars(bars);
      setLoading(false);
    }

    fetchAll();
    return () => { cancelled = true; };
  }, []);

  if (loading) return <SkeletonLoader />;

  if (error) {
    return (
      <div>
        <div className="page-header">
          <h1>Dashboard</h1>
          <p>Overview of your carbon emissions data</p>
        </div>
        <div className="alert alert-error">{error}</div>
      </div>
    );
  }

  return (
    <div>
      {/* ── Page header ── */}
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>Overview of your carbon emissions data</p>
      </div>

      {/* ── Stats ── */}
      <div className="stat-grid">
        <StatCard icon={<Globe size={22} color="#10b981" />}       label="Total CO2e"       value={formatCO2e(stats.totalCO2eKg)}                                              accent="#10b981" />
        <StatCard icon={<FileText size={22} color="#6366f1" />}    label="Emission Records" value={stats.totalRecords.toLocaleString()} unit="total records"                   accent="#6366f1" />
        <StatCard icon={<Clock size={22} color="#f59e0b" />}       label="Pending Review"   value={stats.pendingReviews}                unit="records"                         accent="#f59e0b" />
        <StatCard icon={<CheckCircle size={22} color="#0ea5e9" />} label="High Quality"     value={stats.highQualityPct !== null ? `${stats.highQualityPct}%` : '—'} unit="of recent records" accent="#0ea5e9" />
      </div>

      {/* ── Chart ── */}
      <ScopeChart bars={scopeBars} totalRecords={records.length} />

      {/* ── Recent emission records ── */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <span>Recent Emission Records</span>
          <Link to="/records" className="btn btn-secondary" style={{ fontSize: 12, padding: '4px 10px' }}>
            View all →
          </Link>
        </div>

        {records.length === 0 ? (
          <div className="card-body">
            <div className="empty-state">
              <p>No emission records yet.</p>
              <Link to="/upload" className="btn btn-primary">Upload CSV data</Link>
            </div>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Activity Type</th>
                  <th>Scope</th>
                  <th>Quantity</th>
                  <th>CO2e</th>
                  <th>Quality</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => (
                  <tr key={r.id} className={`dash-row${i % 2 === 1 ? ' row-alt' : ''}`} onClick={() => navigate(`/records/${r.id}`)}>
                    <td className="col-date">{r.activity_date}</td>
                    <td className="col-type">{r.activity_type.replace(/_/g, ' ')}</td>
                    <td><ScopeBadge scope={r.ghg_scope} /></td>
                    <td className="col-qty">{parseFloat(r.quantity_normalized).toFixed(2)} {r.unit_normalized}</td>
                    <td className="col-co2e">{formatCO2e(r.co2e_kg)}</td>
                    <td><QualityBadge score={r.data_quality_score} /></td>
                    <td><StatusBadge status={r.review_status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Recent batches ── */}
      <div className="card">
        <div className="card-header">Recent Ingestion Batches</div>

        {batches.length === 0 ? (
          <div className="card-body">
            <div className="empty-state">
              <p>No uploads yet.</p>
              <Link to="/upload" className="btn btn-primary">Upload your first file</Link>
            </div>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Status</th>
                  <th>Total</th>
                  <th>Successful</th>
                  <th>Failed</th>
                  <th>Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b, i) => (
                  <tr key={b.id} className={i % 2 === 1 ? 'row-alt' : ''}>
                    <td className="col-mono">{b.file_name}</td>
                    <td>
                      <span className={`badge badge-${b.status === 'completed' ? 'approved' : b.status === 'failed' ? 'rejected' : 'pending'}`}>
                        {b.status}
                      </span>
                    </td>
                    <td>{b.total_rows}</td>
                    <td className="col-success">{b.successful_rows}</td>
                    <td className={b.failed_rows > 0 ? 'col-danger' : 'col-muted'}>{b.failed_rows}</td>
                    <td className="col-date">
                      {new Date(b.uploaded_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default Dashboard;
