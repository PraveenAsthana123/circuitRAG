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
    heading: 'Admin',
    items: [
      { href: '/admin', label: 'Operator Dashboard' },
      { href: '/admin/techstack', label: 'Techstack' },
      { href: '/admin/python', label: 'Python (concepts + flow)' },
      { href: '/admin/python/deep', label: 'Python deep dive (interview)' },
      { href: '/admin/llmops', label: 'LLMOps scorecard' },
      { href: '/admin/llmops/deep', label: 'LLMOps deep dive (interview)' },
      { href: '/admin/database/deep', label: 'Database deep dive (interview)' },
      { href: '/admin/database/deep#kafka', label: 'Kafka (event store)' },
      { href: '/admin/mcp/deep', label: 'MCP deep dive (interview)' },
      { href: '/admin/breakers/deep', label: 'Breakers deep dive (interview)' },
      { href: '/admin/rag/deep', label: 'RAG deep dive (interview)' },
      { href: '/admin/microservices/deep', label: 'Microservices deep dive' },
      { href: '/admin/data/deep', label: 'Data preprocessing deep dive' },
      { href: '/admin/deep-dives', label: 'Deep dives — index' },
      { href: '/admin/client-errors', label: 'Client errors (F12 capture)' },
    ],
  },
  {
    heading: 'Stack (tools)',
    items: [
      { href: '/tools/otel-stack', label: 'Observability (OTel + Prom + Jaeger)' },
      { href: '/tools/elk', label: 'ELK (logs)' },
      { href: '/tools/ollama-vllm', label: 'Ollama / vLLM' },
      { href: '/tools/postgres-rls', label: 'Postgres + RLS' },
      { href: '/tools/qdrant', label: 'Qdrant (vector DB)' },
      { href: '/tools/neo4j', label: 'Neo4j (graph DB)' },
      { href: '/tools/redis', label: 'Redis (cache)' },
      { href: '/tools/kafka', label: 'Kafka (event log)' },
      { href: '/tools/istio', label: 'Istio (service mesh)' },
      { href: '/tools/api-gateway', label: 'API Gateway' },
      { href: '/tools/nginx-cdn', label: 'NGINX (edge / CDN)' },
      { href: '/tools/circuit-breakers', label: 'Circuit Breakers (×5)' },
      { href: '/tools/ccb', label: 'Cognitive Circuit Breaker' },
      { href: '/tools/code-governance', label: 'Code governance' },
    ],
  },
  {
    heading: 'RAG quick-jump',
    items: [
      { href: '/admin/rag/deep#chunking', label: 'RAG · Chunking' },
      { href: '/admin/rag/deep#hybrid-retrieval', label: 'RAG · Hybrid retrieval' },
      { href: '/tools/rag-scenarios', label: 'RAG · 36 scenarios' },
    ],
  },
  {
    heading: 'Roles (interview lens)',
    items: [
      { href: '/admin/architect/deep', label: 'Architect — system + ADRs' },
      { href: '/admin/techlead/deep', label: 'Tech Lead — API contract' },
      { href: '/admin/eng-manager/deep', label: 'Eng Manager — roadmap + risk' },
      { href: '/admin/technical-plan/deep', label: 'Technical Plan — BRD-to-code' },
    ],
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
