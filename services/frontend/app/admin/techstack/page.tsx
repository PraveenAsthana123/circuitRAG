'use client';

/**
 * Techstack inventory — read-only view of installed pip/npm packages
 * vs pending. Operators check this before saying "we need to add X"
 * — answer is in the panel, not in their head.
 *
 * Hard call: this is a separate route from /admin (not a 6th panel
 * jammed in) because that file is at 6 commits already, and a
 * full-width grouped table reads better with its own page than as
 * a card mixed with breaker / tools / prompts.
 *
 * No install buttons. The page is informational; if the operator
 * wants a pending tool installed, they run `pip install X` or
 * `npm install X` themselves. That keeps the security surface
 * minimal — the UI never triggers package mutations.
 */

import { useEffect, useRef, useState } from 'react';
import {
  api,
  ApiError,
  type HealthTechstackResponse,
  type TechstackEntry,
} from '../../../lib/api';

const REFRESH_INTERVAL_MS = 30_000;

function installCommand(e: TechstackEntry): string {
  if (e.source === 'pip') return `pip install ${e.name}`;
  if (e.source === 'npm') return `npm install ${e.name}`;
  return `# install ${e.name} via ${e.source}`;
}

function groupBy(
  entries: TechstackEntry[],
  key: (e: TechstackEntry) => string,
): Map<string, TechstackEntry[]> {
  const map = new Map<string, TechstackEntry[]>();
  for (const e of entries) {
    const k = key(e);
    const arr = map.get(k);
    if (arr) arr.push(e);
    else map.set(k, [e]);
  }
  return map;
}

export default function TechstackPage() {
  const [data, setData] = useState<HealthTechstackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'installed' | 'pending'>('all');
  const [search, setSearch] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      abortRef.current?.abort();
      const ctl = new AbortController();
      abortRef.current = ctl;
      try {
        const resp = await api.healthTechstack(ctl.signal);
        if (cancelled) return;
        setData(resp);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError) {
          setError(`${e.status} ${e.errorCode}: ${e.detail}`);
        } else if ((e as Error).name !== 'AbortError') {
          setError((e as Error).message);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    // Slower refresh than /admin (30s vs 5s) — package state changes
    // on the order of installs, not seconds.
    const id = setInterval(load, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
      abortRef.current?.abort();
    };
  }, []);

  const filtered = (data?.entries ?? [])
    .filter((e) => {
      if (filter === 'installed' && !e.installed) return false;
      if (filter === 'pending' && e.installed) return false;
      if (search) {
        const q = search.toLowerCase();
        return (
          e.name.toLowerCase().includes(q)
          || e.category.toLowerCase().includes(q)
          || e.purpose.toLowerCase().includes(q)
        );
      }
      return true;
    });
  const grouped = groupBy(filtered, (e) => e.category);
  const sortedCategories = Array.from(grouped.keys()).sort();

  return (
    <>
      <div className="page-header">
        <div className="page-header-copy">
          <h1 className="section-title">Techstack inventory</h1>
          <p className="page-subtitle">
            Read-only view of installed pip / npm packages vs pending.
            Auto-refreshes every {REFRESH_INTERVAL_MS / 1000}s. No
            installs from the UI — copy the install command and run
            it yourself.
          </p>
        </div>
      </div>

      <div className="metrics-strip">
        <div className="metric-card">
          <div className="metric-label">Installed</div>
          <div className="metric-value">{data?.installed_count ?? '—'}</div>
          <div className="field-help">across the curated catalog</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Pending</div>
          <div className="metric-value">{data?.pending_count ?? '—'}</div>
          <div className="field-help">not detected in the running env</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Total tracked</div>
          <div className="metric-value">{data?.entries.length ?? '—'}</div>
          <div className="field-help">curated entries (catalog)</div>
        </div>
      </div>

      {error && (
        <div className="card" role="alert" style={{ borderColor: '#fecaca' }}>
          <strong>Endpoint unreachable.</strong>
          <div className="field-help" style={{ marginTop: 8 }}>
            {error}
          </div>
        </div>
      )}

      {/* Filter / search controls. */}
      <div
        className="card"
        style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}
      >
        <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="field-help">Show</span>
          <select
            value={filter}
            onChange={(e) =>
              setFilter(e.target.value as 'all' | 'installed' | 'pending')
            }
            style={{
              padding: '4px 8px',
              border: '1px solid #d1d5db',
              borderRadius: 4,
            }}
          >
            <option value="all">all</option>
            <option value="installed">installed only</option>
            <option value="pending">pending only</option>
          </select>
        </label>
        <input
          type="text"
          placeholder="search by name / category / purpose"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search techstack"
          style={{
            flex: '1 1 240px',
            padding: '6px 10px',
            border: '1px solid #d1d5db',
            borderRadius: 4,
            fontSize: 13,
          }}
        />
      </div>

      {loading && !data ? (
        <div className="card list-empty">
          <span className="spinner" /> Loading…
        </div>
      ) : (
        sortedCategories.map((category) => {
          const rows = grouped.get(category) ?? [];
          return (
            <div key={category} className="card">
              <div className="card-header" style={{ marginBottom: 12 }}>
                <strong>{category}</strong>{' '}
                <span className="field-help">
                  ({rows.filter((r) => r.installed).length}/{rows.length} installed)
                </span>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Package</th>
                      <th>Source</th>
                      <th>Status</th>
                      <th>Version</th>
                      <th>Purpose</th>
                      <th>Install command</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e: TechstackEntry) => (
                      <tr key={`${e.source}::${e.name}`}>
                        <td>
                          <code>{e.name}</code>
                        </td>
                        <td>
                          <span className="field-help">{e.source}</span>
                        </td>
                        <td>
                          {e.installed ? (
                            <span className="badge badge-active">installed</span>
                          ) : (
                            <span className="badge badge-parsing">pending</span>
                          )}
                        </td>
                        <td>
                          {e.version ?? <span className="field-help">—</span>}
                        </td>
                        <td>{e.purpose}</td>
                        <td>
                          {e.installed ? (
                            <span className="field-help">—</span>
                          ) : (
                            <code style={{ fontSize: 12 }}>
                              {installCommand(e)}
                            </code>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })
      )}
    </>
  );
}
