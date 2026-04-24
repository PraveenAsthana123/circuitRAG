'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/upload', label: 'Upload' },
  { href: '/documents', label: 'Documents' },
  { href: '/ask', label: 'Ask' },
  { href: '/tools', label: 'Tools' },
  { href: '/tools/system-design', label: '↳ System Design' },
  { href: '/tools/design-areas', label: '↳ 74 Design Features' },
  { href: '/tools/circuit-breakers-list', label: '↳ Circuit Breakers' },
  { href: '/tools/microservice-scenarios', label: '↳ Microservice Scenarios' },
  { href: '/tools/methodologies', label: '↳ Methodologies (TDD/BDD/…)' },
  { href: '/tools/code-governance', label: '↳ Code Governance' },
  { href: '/tools/database-scenarios', label: '↳ Database Scenarios' },
  { href: '/tools/scenarios', label: '↳ All Scenarios Catalog' },
  { href: '/admin', label: 'Admin' },
];

/** Left-menu nav. The active link gets the accent border. */
export default function Sidebar() {
  const pathname = usePathname();
  return (
    <ul className="sidebar-nav">
      {LINKS.map((link) => {
        const active = pathname === link.href || pathname.startsWith(link.href + '/');
        return (
          <li key={link.href}>
            <Link href={link.href} className={active ? 'active' : ''}>
              {link.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
