import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { getEmissionRecord } from '../api';
import './RecordDetail.css';

const SCOPE_LABELS = { 1: 'Scope 1 — Direct emissions', 2: 'Scope 2 — Indirect energy', 3: 'Scope 3 — Value chain' };
const SCOPE3_CATEGORIES = {
  1: 'Purchased goods & services', 2: 'Capital goods', 3: 'Fuel & energy', 4: 'Upstream transport',
  5: 'Waste', 6: 'Business travel', 7: 'Employee commuting', 8: 'Upstream leased assets',
  9: 'Downstream transport', 10: 'Processing of sold products', 11: 'Use of sold products',
  12: 'End-of-life treatment', 13: 'Downstream leased assets', 14: 'Franchises', 15: 'Investments',
};

function Field({ label, value, mono, wide }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div style={{ gridColumn: wide ? 'span 2' : undefined }}>
      <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px', color: 'var(--slate-400)', marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, color: 'var(--slate-800)', fontFamily: mono ? 'monospace' : undefined, wordBreak: 'break-all' }}>
        {value}
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-header">{title}</div>
      <div className="card-body">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px 24px' }}>
          {children}
        </div>
      </div>
    </div>
  );
}

function RecordDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [record, setRecord] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getEmissionRecord(id).then(({ data, error: fetchError }) => {
      if (cancelled) return;
      if (data) setRecord(data);
      if (fetchError) setError(typeof fetchError === 'string' ? fetchError : fetchError.detail ?? 'Failed to load record.');
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [id]);

  if (loading) return <div className="loading">Loading record…</div>;

  if (error) {
    return (
      <div>
        <button className="btn btn-secondary" onClick={() => navigate('/records')} style={{ marginBottom: 20 }}>← Back to Records</button>
        <div className="alert alert-error">{error}</div>
      </div>
    );
  }

  if (!record) {
    return (
      <div>
        <button className="btn btn-secondary" onClick={() => navigate('/records')} style={{ marginBottom: 20 }}>← Back to Records</button>
        <div className="alert alert-error">Record not found.</div>
      </div>
    );
  }

  const co2eTonnes = (parseFloat(record.co2e_kg) / 1000).toFixed(4);
  const hasMetadata = record.metadata && Object.keys(record.metadata).length > 0;
  const hasQualityFlags = record.quality_flags?.length > 0;

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ marginBottom: 24 }}>
        <button className="btn btn-secondary" onClick={() => navigate('/records')} style={{ marginBottom: 14 }}>
          ← Back to Records
        </button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--slate-900)', marginBottom: 4 }}>
              {record.activity_type.replace(/_/g, ' ')}
            </h1>
            <div style={{ fontSize: 13, color: 'var(--slate-400)', fontFamily: 'monospace' }}>{record.id}</div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className={`badge badge-scope-${record.ghg_scope}`} style={{ fontSize: 12, padding: '4px 10px' }}>
              Scope {record.ghg_scope}
            </span>
            <span className={`badge badge-${record.review_status}`} style={{ fontSize: 12, padding: '4px 10px' }}>
              {record.review_status.replace('_', ' ')}
            </span>
            <span className={`badge badge-${record.data_quality_score}`} style={{ fontSize: 12, padding: '4px 10px' }}>
              {record.data_quality_score} quality
            </span>
            {record.is_audit_locked && (
              <span className="badge" style={{ background: '#fef9c3', color: '#854d0e', fontSize: 12, padding: '4px 10px' }}>
                🔒 Audit locked
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── CO2e hero ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16, marginBottom: 20 }}>
        {[
          { label: 'Total CO2e', value: `${parseFloat(record.co2e_kg).toFixed(2)} kg`, accent: '#16a34a' },
          { label: 'CO2e (tonnes)', value: `${co2eTonnes} t CO2e`, accent: '#6366f1' },
          { label: 'Emission Factor', value: `${record.emission_factor_value} kg/unit`, accent: '#0ea5e9' },
          { label: 'Activity Date', value: record.activity_date, accent: '#f59e0b' },
        ].map(({ label, value, accent }) => (
          <div key={label} className="stat-card" style={{ borderTop: `3px solid ${accent}` }}>
            <div className="label">{label}</div>
            <div style={{ fontWeight: 700, fontSize: 18, color: 'var(--slate-900)', marginTop: 4 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* ── Activity ── */}
      <Section title="Activity Information">
        <Field label="Activity Type" value={record.activity_type} />
        <Field label="Activity Date" value={record.activity_date} />
        {record.activity_end_date && <Field label="Activity End Date" value={record.activity_end_date} />}
        <Field label="GHG Scope" value={SCOPE_LABELS[record.ghg_scope] ?? `Scope ${record.ghg_scope}`} />
        {record.scope3_category && (
          <Field label="Scope 3 Category" value={`Category ${record.scope3_category} — ${SCOPE3_CATEGORIES[record.scope3_category] ?? ''}`} />
        )}
        {record.location_name && <Field label="Location" value={record.location_name} />}
        {record.location_code && <Field label="Location Code" value={record.location_code} />}
        {record.country_code && <Field label="Country Code" value={record.country_code} />}
      </Section>

      {/* ── Quantities ── */}
      <Section title="Quantities & Emissions">
        <Field label="Original Quantity" value={`${record.quantity_original} ${record.unit_original}`} />
        <Field label="Normalized Quantity" value={`${parseFloat(record.quantity_normalized).toFixed(4)} ${record.unit_normalized}`} />
        <Field label="Emission Factor Value" value={`${record.emission_factor_value} kg CO2e / ${record.unit_normalized}`} />
        <Field label="Total CO2e" value={`${parseFloat(record.co2e_kg).toFixed(4)} kg`} />
        {record.emission_factor_details && (
          <>
            <Field label="Factor Type" value={record.emission_factor_details.factor_type} />
            <Field label="Factor Source" value={record.emission_factor_details.source} />
            <Field label="Factor Region" value={record.emission_factor_details.region} />
            <Field label="Factor Valid From" value={record.emission_factor_details.valid_from} />
            {record.emission_factor_details.valid_until && (
              <Field label="Factor Valid Until" value={record.emission_factor_details.valid_until} />
            )}
          </>
        )}
      </Section>

      {/* ── Review & quality ── */}
      <Section title="Review & Quality">
        <Field label="Review Status" value={
          <span className={`badge badge-${record.review_status}`}>{record.review_status.replace('_', ' ')}</span>
        } />
        <Field label="Data Quality Score" value={
          <span className={`badge badge-${record.data_quality_score}`}>{record.data_quality_score}</span>
        } />
        {record.reviewed_by_username && <Field label="Reviewed By" value={record.reviewed_by_username} />}
        {record.reviewed_at && <Field label="Reviewed At" value={new Date(record.reviewed_at).toLocaleString()} />}
        {record.review_notes && <Field label="Review Notes" value={record.review_notes} wide />}
        <Field label="Audit Locked" value={record.is_audit_locked ? '🔒 Yes — record cannot be edited' : '🔓 No'} />
        {record.locked_by_username && <Field label="Locked By" value={record.locked_by_username} />}
        {record.locked_at && <Field label="Locked At" value={new Date(record.locked_at).toLocaleString()} />}
      </Section>

      {/* ── Quality flags ── */}
      {hasQualityFlags && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">Quality Flags</div>
          <div className="card-body">
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
              {record.quality_flags.map((flag, i) => (
                <li key={i} style={{ fontSize: 13, color: 'var(--slate-700)' }}>{flag}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* ── Source metadata ── */}
      {hasMetadata && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-header">Source Metadata</div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '12px 24px' }}>
              {Object.entries(record.metadata).map(([key, val]) => (
                <Field key={key} label={key.replace(/_/g, ' ')} value={String(val)} />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Provenance ── */}
      <Section title="Provenance">
        <Field label="Record ID" value={record.id} mono />
        <Field label="Ingestion Batch" value={record.ingestion_batch_file_name ?? record.ingestion_batch} mono />
        <Field label="Created At" value={record.created_at ? new Date(record.created_at).toLocaleString() : undefined} />
        <Field label="Last Updated" value={record.updated_at ? new Date(record.updated_at).toLocaleString() : undefined} />
      </Section>

      {/* ── Footer nav ── */}
      <div style={{ marginTop: 8, paddingBottom: 8 }}>
        <button className="btn btn-secondary" onClick={() => navigate('/records')}>← Back to Records</button>
      </div>
    </div>
  );
}

export default RecordDetail;
