import { useState, useEffect, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle } from 'lucide-react';
import { getDataSources, uploadCSV } from '../api';
import './Upload.css';

const SOURCE_TYPE_LABELS = {
  sap_procurement: 'SAP Procurement',
  utility_electricity: 'Utility Electricity',
  corporate_travel: 'Corporate Travel',
};

function UploadResult({ result }) {
  const hasErrors = result.errors?.length > 0;

  return (
    <div className={`alert ${result.failed_rows > 0 ? 'alert-info' : 'alert-success'}`}
         style={{ marginTop: 24 }}>
      <div style={{ fontWeight: 600, marginBottom: 12, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8 }}>
        {result.failed_rows === 0
          ? <><CheckCircle size={16} /> Upload complete</>
          : <><AlertCircle size={16} /> Upload completed with errors</>}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: hasErrors ? 16 : 0 }}>
        {[
          { label: 'Status', value: result.status },
          { label: 'Total rows', value: result.total_rows },
          { label: 'Successful', value: result.successful_rows },
          { label: 'Failed', value: result.failed_rows },
          { label: 'Records created', value: result.normalized_records ?? '—' },
        ].map(({ label, value }) => (
          <div key={label} style={{ background: 'rgba(255,255,255,0.6)', borderRadius: 6, padding: '8px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px', opacity: 0.7, marginBottom: 2 }}>{label}</div>
            <div style={{ fontWeight: 700, fontSize: 16 }}>{value}</div>
          </div>
        ))}
      </div>

      {hasErrors && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer', fontWeight: 500, fontSize: 13 }}>
            {result.errors.length} error{result.errors.length !== 1 ? 's' : ''} — click to expand
          </summary>
          <ul style={{ margin: '8px 0 0 16px', fontSize: 12, lineHeight: 1.7 }}>
            {result.errors.map((e, i) => (
              <li key={i}>{typeof e === 'object' ? `Row ${e.row}: ${e.errors?.join(', ')}` : e}</li>
            ))}
          </ul>
        </details>
      )}

      <div style={{ marginTop: 12, fontSize: 12, opacity: 0.8 }}>
        Batch ID: <code style={{ fontFamily: 'monospace' }}>{result.batch_id}</code>
      </div>
    </div>
  );
}

function Upload() {
  const [dataSources, setDataSources]     = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState('');
  const [file, setFile]                   = useState(null);
  const [dragOver, setDragOver]           = useState(false);
  const [uploading, setUploading]         = useState(false);
  const [result, setResult]               = useState(null);
  const [error, setError]                 = useState(null);
  const fileInputRef = useRef(null);
  const formRef = useRef(null);

  useEffect(() => {
    getDataSources({ is_active: true }).then(({ data, error }) => {
      if (data) setDataSources(data.results ?? []);
      if (error) setError('Could not load data sources. Is the backend running?');
      setSourcesLoading(false);
    });
  }, []);

  const applyFile = (f) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.csv')) {
      setError('Only CSV files are accepted.');
      setFile(null);
      return;
    }
    setFile(f);
    setError(null);
    setResult(null);
  };

  const handleFileInput = (e) => applyFile(e.target.files[0]);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    applyFile(e.dataTransfer.files[0]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file || !selectedSource) {
      setError('Please select both a data source and a CSV file.');
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);

    const { data, error: uploadError } = await uploadCSV(file, selectedSource);

    if (data) {
      setResult(data);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }

    if (uploadError) {
      const msg =
        typeof uploadError === 'string'
          ? uploadError
          : uploadError.error ?? uploadError.detail ?? JSON.stringify(uploadError);
      setError(msg);
    }

    setUploading(false);
  };

  return (
    <div>
      <div className="page-header">
        <h1>Upload Emissions Data</h1>
        <p>Import SAP procurement, utility electricity, or corporate travel CSV files</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 24, alignItems: 'start' }}>

        {/* ── Upload form ── */}
        <div className="card">
          <div className="card-header">CSV File Upload</div>
          <div className="card-body">
            <form ref={formRef} onSubmit={handleSubmit}>

              {/* Data source selector */}
              <div className="form-group">
                <label className="form-label" htmlFor="dataSource">Data Source</label>
                {sourcesLoading ? (
                  <div style={{ color: 'var(--slate-400)', fontSize: 13 }}>Loading sources…</div>
                ) : (
                  <select
                    id="dataSource"
                    className="form-control"
                    value={selectedSource}
                    onChange={(e) => setSelectedSource(e.target.value)}
                    required
                  >
                    <option value="">— Select a data source —</option>
                    {dataSources.map((src) => (
                      <option key={src.id} value={src.id}>
                        {src.name} · {SOURCE_TYPE_LABELS[src.source_type] ?? src.source_type}
                      </option>
                    ))}
                  </select>
                )}
                {!sourcesLoading && dataSources.length === 0 && !error && (
                  <p style={{ fontSize: 12, color: 'var(--slate-400)', marginTop: 6 }}>
                    No active data sources found. Create one in the admin panel first.
                  </p>
                )}
              </div>

              {/* Drop zone */}
              <div className="form-group">
                <label className="form-label">CSV File</label>
                <div
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  style={{
                    border: `2px dashed ${dragOver ? 'var(--green-600)' : file ? 'var(--green-600)' : 'var(--slate-200)'}`,
                    borderRadius: 8,
                    padding: '28px 20px',
                    textAlign: 'center',
                    cursor: 'pointer',
                    background: dragOver ? 'var(--green-50)' : file ? 'var(--green-50)' : 'var(--slate-50)',
                    transition: 'all 0.15s',
                    userSelect: 'none',
                  }}
                >
                  {file ? (
                    <>
                      <div style={{ marginBottom: 8, color: 'var(--primary-dark)' }}><FileText size={32} /></div>
                      <div style={{ fontWeight: 600, color: 'var(--text)' }}>{file.name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                        {(file.size / 1024).toFixed(1)} KB — click to change
                      </div>
                    </>
                  ) : (
                    <>
                      <div style={{ marginBottom: 10, color: 'var(--text-muted)' }}><UploadCloud size={36} /></div>
                      <div style={{ fontWeight: 500, color: 'var(--text)' }}>
                        Drag & drop a CSV file here
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                        or click to browse
                      </div>
                    </>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileInput}
                  style={{ display: 'none' }}
                />
              </div>

              {error && <div className="alert alert-error">{error}</div>}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={uploading || !file || !selectedSource}
                style={{ width: '100%', justifyContent: 'center', padding: '10px 0' }}
              >
                {uploading ? 'Uploading…' : 'Upload & Process'}
              </button>
            </form>

            {result && <UploadResult result={result} />}
          </div>
        </div>

        {/* ── Help sidebar ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card">
            <div className="card-header">Accepted Formats</div>
            <div className="card-body" style={{ fontSize: 13, lineHeight: 1.7 }}>
              <p style={{ marginBottom: 10, color: 'var(--slate-600)' }}>Each source type expects specific columns:</p>
              <div style={{ marginBottom: 10 }}>
                <strong>SAP Procurement</strong>
                <div style={{ color: 'var(--slate-500)', fontSize: 12 }}>Material, Material Description, Quantity, Unit, Posting Date, Plant</div>
              </div>
              <div style={{ marginBottom: 10 }}>
                <strong>Utility Electricity</strong>
                <div style={{ color: 'var(--slate-500)', fontSize: 12 }}>Meter, Account Number, Bill Period, kWh, Site, Country</div>
              </div>
              <div>
                <strong>Corporate Travel</strong>
                <div style={{ color: 'var(--slate-500)', fontSize: 12 }}>Date, Employee, From, To, Distance, Mode, Flight Class</div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-header">What happens next?</div>
            <div className="card-body" style={{ fontSize: 13, color: 'var(--slate-600)', lineHeight: 1.8 }}>
              <ol style={{ paddingLeft: 16 }}>
                <li>CSV rows are validated</li>
                <li>Data is normalised to standard units</li>
                <li>Emission factors are applied</li>
                <li>CO2e values are calculated</li>
                <li>Quality checks run automatically</li>
                <li>Records appear in Emissions Records</li>
              </ol>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

export default Upload;
