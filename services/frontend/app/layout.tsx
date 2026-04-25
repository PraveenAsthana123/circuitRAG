import type { Metadata } from 'next';
import Link from 'next/link';
import { ReactNode } from 'react';
import '../styles/globals.css';
import Sidebar from '../components/Sidebar';
import ClientErrorReporter from '../components/ClientErrorReporter';
import ErrorBoundary from '../components/ErrorBoundary';

export const metadata: Metadata = {
  title: 'DocuMind',
  description: 'AI-powered enterprise document intelligence',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Mounted once per tab; installs window.onerror +
            unhandledrejection handlers that POST to
            /api/v1/admin/client-errors. */}
        <ClientErrorReporter />
        <ErrorBoundary>
          <div className="app-shell">
            <aside className="sidebar" aria-label="Primary navigation">
              <div className="sidebar-brand">DocuMind</div>
              <Sidebar />
            </aside>
            <header className="topbar">
              <details className="mobile-nav">
                {/*
                  aria-label gives screen readers a name for the disclosure;
                  the visual label is the icon-glyph below. The drawer-panel
                  gets aria-hidden flipped via [open] in CSS.
                */}
                <summary
                  className="mobile-nav-toggle"
                  aria-label="Toggle navigation menu"
                >
                  <span aria-hidden="true">☰</span>
                  <span className="mobile-nav-toggle-text">Menu</span>
                </summary>
                <div className="mobile-nav-backdrop" aria-hidden="true" />
                <div className="mobile-nav-panel">
                  <Sidebar />
                </div>
              </details>
              {/* Topbar brand renders only on mobile (sidebar carries it on desktop). */}
              <span className="brand brand-mobile-only">DocuMind</span>
              <span className="spacer" />
              <span className="tenant-pill" title="Active tenant">demo-tenant</span>
              <Link href="/admin" className="topbar-link">Admin</Link>
            </header>
            <main className="content" id="main-content">
              <div className="content-inner">{children}</div>
            </main>
          </div>
        </ErrorBoundary>
      </body>
    </html>
  );
}
