import { useState, useEffect, useRef } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, NavLink } from 'react-router-dom';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import {
  Leaf, LayoutDashboard, Upload as UploadIcon, ClipboardList,
  Settings as SettingsIcon, Bell, Sun, Moon, ChevronDown, Menu, Info,
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import Upload from './pages/Upload';
import RecordsList from './pages/RecordsList';
import RecordDetail from './pages/RecordDetail';
import SettingsPage from './pages/Settings';
import './App.css';

const NAV_ITEMS = [
  { to: '/',         end: true,  Icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/upload',   end: false, Icon: UploadIcon,      label: 'Upload Data' },
  { to: '/records',  end: false, Icon: ClipboardList,   label: 'Emissions Records' },
  { to: '/settings', end: false, Icon: SettingsIcon,    label: 'Settings' },
];

// ── Sidebar ───────────────────────────────────────────────────────────────────
function Sidebar({ mobileOpen, onClose }) {
  return (
    <>
      {mobileOpen && (
        <div className="sidebar-overlay" onClick={onClose} aria-hidden="true" />
      )}

      <aside className={`sidebar${mobileOpen ? ' sidebar--open' : ''}`}>
        <div className="sidebar-brand-wrap">
          <Link to="/" className="sidebar-brand" onClick={onClose}>
            <span className="sidebar-brand-icon"><Leaf size={28} color="#10b981" strokeWidth={2} /></span>
            <span className="sidebar-brand-name">Breathe ESG</span>
          </Link>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {NAV_ITEMS.map(({ to, end, Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `sidebar-link${isActive ? ' sidebar-link--active' : ''}`
              }
              onClick={onClose}
            >
              <span className="sidebar-link-icon" aria-hidden="true"><Icon size={18} /></span>
              <span className="sidebar-link-label">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="sidebar-footer-text">
            v1.0 · Demo
            <span
              className="sidebar-footer-info"
              title="Demo version for assignment evaluation"
              aria-label="Demo version for assignment evaluation"
            >
              <Info size={11} />
            </span>
          </span>
        </div>
      </aside>
    </>
  );
}

// ── Top bar ───────────────────────────────────────────────────────────────────
function TopBar({ onMenuToggle }) {
  const { theme, toggleTheme } = useTheme();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    if (!dropdownOpen) return;
    function onOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, [dropdownOpen]);

  return (
    <header className="topbar">
      <button className="topbar-menu-btn" onClick={onMenuToggle} aria-label="Toggle sidebar">
        <Menu size={18} />
      </button>

      <div className="topbar-right">
        <button className="topbar-icon-btn" aria-label="Notifications" title="Notifications">
          <Bell size={18} />
        </button>

        <button
          className="topbar-icon-btn"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
          title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        >
          {theme === 'light' ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        <div className="topbar-profile" ref={dropdownRef}>
          <button
            className={`topbar-user${dropdownOpen ? ' topbar-user--open' : ''}`}
            onClick={() => setDropdownOpen(o => !o)}
            aria-haspopup="true"
            aria-expanded={dropdownOpen}
          >
            <div className="topbar-avatar">S</div>
            <ChevronDown
              size={14}
              className="topbar-chevron"
              style={{ transform: dropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s ease' }}
            />
          </button>

          {dropdownOpen && (
            <div className="topbar-dropdown" role="menu">
              <div className="topbar-dropdown-header">User</div>
              <div className="topbar-dropdown-divider" />
              <button className="topbar-dropdown-item" role="menuitem"
                onClick={() => { alert('Feature not available in demo'); setDropdownOpen(false); }}>
                Profile
              </button>
              <button className="topbar-dropdown-item" role="menuitem"
                onClick={() => { alert('Feature not available in demo'); setDropdownOpen(false); }}>
                Settings
              </button>
              <div className="topbar-dropdown-divider" />
              <button className="topbar-dropdown-item topbar-dropdown-item--danger" role="menuitem"
                onClick={() => { alert('Authentication not implemented in demo'); setDropdownOpen(false); }}>
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

// ── App layout ────────────────────────────────────────────────────────────────
function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="app-layout">
      <Sidebar mobileOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="app-body">
        <TopBar onMenuToggle={() => setSidebarOpen(o => !o)} />

        <main className="main-content">
          <Routes>
            <Route path="/"            element={<Dashboard />} />
            <Route path="/upload"      element={<Upload />} />
            <Route path="/records"     element={<RecordsList />} />
            <Route path="/records/:id" element={<RecordDetail />} />
            <Route path="/settings"    element={<SettingsPage />} />
          </Routes>
        </main>

        <footer className="footer">
          <p>Breathe ESG &copy; {new Date().getFullYear()} — Carbon Emissions Tracking Platform</p>
        </footer>
      </div>
    </div>
  );
}

// ── Root ──────────────────────────────────────────────────────────────────────
function App() {
  return (
    <ThemeProvider>
      <Router>
        <AppLayout />
      </Router>
    </ThemeProvider>
  );
}

export default App;
