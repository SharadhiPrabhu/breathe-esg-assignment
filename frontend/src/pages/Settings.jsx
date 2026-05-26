import { User, Building2, Bell, Database, Download, Lock, ChevronRight } from 'lucide-react';
import './Settings.css';

const SECTIONS = [
  {
    Icon: User,
    title: 'User Profile',
    description: 'Manage your name, email, password, and personal preferences.',
    color: '#6366f1',
  },
  {
    Icon: Building2,
    title: 'Organization Settings',
    description: 'Configure your organization name, logo, industry, and reporting year.',
    color: '#10b981',
  },
  {
    Icon: Bell,
    title: 'Notification Preferences',
    description: 'Control email and in-app alerts for data quality issues and batch completions.',
    color: '#f59e0b',
  },
  {
    Icon: Database,
    title: 'Data Sources',
    description: 'Add, edit, or deactivate connected data sources and manage column mappings.',
    color: '#3b82f6',
  },
  {
    Icon: Download,
    title: 'Export Settings',
    description: 'Configure default export formats, date ranges, and GHG report templates.',
    color: '#8b5cf6',
  },
];

function Settings() {
  return (
    <div>
      <div className="page-header">
        <h1>Settings</h1>
        <p>Configure your account and application preferences</p>
      </div>

      <div className="settings-grid">
        {SECTIONS.map(({ Icon, title, description, color }) => (
          <div key={title} className="settings-card">
            <div className="settings-card-icon" style={{ background: `${color}18`, color }}>
              <Icon size={20} />
            </div>
            <div className="settings-card-body">
              <div className="settings-card-title">{title}</div>
              <div className="settings-card-desc">{description}</div>
            </div>
            <div className="settings-card-end">
              <span className="settings-soon-badge">Coming Soon</span>
              <ChevronRight size={16} className="settings-chevron" />
            </div>
          </div>
        ))}
      </div>

      <div className="settings-note">
        <Lock size={13} />
        Settings are read-only in this demo. Full configuration will be available in the production release.
      </div>
    </div>
  );
}

export default Settings;
