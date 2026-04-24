'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

type Entry = { href: string; label: string };
type Group = { heading?: string; items: Entry[] };

const GROUPS: Group[] = [
  {
    items: [
      { href: '/upload', label: 'Upload' },
      { href: '/documents', label: 'Documents' },
      { href: '/ask', label: 'Ask' },
    ],
  },
  {
    heading: 'Tools',
    items: [
      { href: '/tools', label: 'Tool index' },
      { href: '/tools/system-design', label: 'System Design' },
      { href: '/tools/design-areas', label: '74 Design Features' },
      { href: '/tools/scenarios', label: 'All Scenarios Catalog' },
    ],
  },
  {
    heading: 'Catalogs',
    items: [
      { href: '/tools/circuit-breakers-list', label: 'Circuit Breakers' },
      { href: '/tools/rag-scenarios', label: '36 RAG Scenarios' },
      { href: '/tools/microservice-scenarios', label: 'Microservice Scenarios' },
      { href: '/tools/database-scenarios', label: 'Database Scenarios' },
      { href: '/tools/methodologies', label: 'Methodologies' },
      { href: '/tools/code-governance', label: 'Code Governance' },
    ],
  },
  {
    items: [{ href: '/admin', label: 'Admin' }],
  },
];

/** Left-menu nav. Grouped so the 10+ links are scannable. */
export default function Sidebar() {
  const pathname = usePathname();
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + '/');
  return (
    <nav className="sidebar-nav">
      {GROUPS.map((g, gi) => (
        <div key={gi} className="sidebar-group">
          {g.heading && <div className="sidebar-heading">{g.heading}</div>}
          <ul>
            {g.items.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className={isActive(link.href) ? 'active' : ''}>
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
