'use client';

import { useState } from 'react';
import type { Tool } from '../lib/tools';
import Markdownish from './Markdownish';

const TAB_ORDER: Array<{ key: keyof Tool['tabs']; label: string }> = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'feature', label: 'Feature' },
  { key: 'benefitMonitoring', label: 'Benefit + Monitoring' },
  { key: 'integration', label: 'Integration' },
  { key: 'visualization', label: 'Visualization' },
  { key: 'interview', label: 'Interview' },
];

export default function ToolTabs({ tool }: { tool: Tool }) {
  const [active, setActive] = useState<keyof Tool['tabs']>('dashboard');
  const current = tool.tabs[active];
  return (
    <div className="tool-tabs">
      <div className="tool-tabs-strip" role="tablist">
        {TAB_ORDER.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={active === key}
            className={`tool-tab${active === key ? ' tool-tab-active' : ''}`}
            onClick={() => setActive(key)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="tool-tab-panel" role="tabpanel">
        <h3 className="tool-tab-title">{current.title}</h3>
        <Markdownish body={current.body} />
      </div>
    </div>
  );
}
