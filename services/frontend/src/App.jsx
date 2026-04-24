import { Link, NavLink, Navigate, Route, Routes } from 'react-router-dom';
import UploadPage from './pages/UploadPage.jsx';
import DocumentsPage from './pages/DocumentsPage.jsx';
import AskPage from './pages/AskPage.jsx';
import AdminPage from './pages/AdminPage.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';

export default function App() {
  return (
    <ErrorBoundary>
      <div className="app-shell">
        <aside className="sidebar">
          <div style={{ padding: '0 24px 20px', fontSize: '1.25rem', fontWeight: 600 }}>
            DocuMind
          </div>
          <ul className="sidebar-nav">
            <li><NavLink to="/upload" className={({ isActive }) => isActive ? 'active' : ''}>Upload</NavLink></li>
            <li><NavLink to="/documents" className={({ isActive }) => isActive ? 'active' : ''}>Documents</NavLink></li>
            <li><NavLink to="/ask" className={({ isActive }) => isActive ? 'active' : ''}>Ask</NavLink></li>
            <li><NavLink to="/admin" className={({ isActive }) => isActive ? 'active' : ''}>Admin</NavLink></li>
          </ul>
        </aside>
        <header className="topbar">
          <span className="brand">DocuMind</span>
          <span className="spacer" />
          <span className="tenant-pill">tenant: demo-tenant</span>
          <Link to="/admin" style={{ color: 'inherit', opacity: 0.85 }}>admin</Link>
        </header>
        <main className="content">
          <div className="content-inner">
            <Routes>
              <Route path="/" element={<Navigate to="/ask" replace />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/ask" element={<AskPage />} />
              <Route path="/admin" element={<AdminPage />} />
              <Route path="*" element={<div className="list-empty">Page not found.</div>} />
            </Routes>
          </div>
        </main>
      </div>
    </ErrorBoundary>
  );
}
