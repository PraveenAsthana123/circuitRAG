import type { Metadata } from 'next';
import Link from 'next/link';
import { ReactNode } from 'react';
import '../styles/globals.css';
import Sidebar from '../components/Sidebar';

export const metadata: Metadata = {
  title: 'DocuMind',
  description: 'AI-powered enterprise document intelligence',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="sidebar-brand">DocuMind</div>
            <Sidebar />
          </aside>
          <header className="topbar">
            <span className="brand">DocuMind</span>
            <span className="spacer" />
            <span className="tenant-pill">tenant: demo-tenant</span>
            <Link href="/admin" style={{ color: 'inherit', opacity: 0.85 }}>admin</Link>
          </header>
          <main className="content">
            <div className="content-inner">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
