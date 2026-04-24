'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/upload', label: 'Upload' },
  { href: '/documents', label: 'Documents' },
  { href: '/ask', label: 'Ask' },
  { href: '/tools', label: 'Tools' },
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
