import Link from 'next/link';
import os from 'node:os';

import { getSidecarEventById } from '@/lib/sidecar';

type Props = {
  params: Promise<{
    eventId: string;
  }>;
};

function parseAdvisorOutput(raw: string | null): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export default async function SidecarEventDetailPage({ params }: Props) {
  const { eventId: rawEventId } = await params;
  const eventId = Number(rawEventId);
  const event = Number.isInteger(eventId) && eventId > 0 ? await getSidecarEventById(eventId) : null;

  if (!event) {
    return (
      <div style={{ padding: 24 }}>
        <h1>Sidecar event not found</h1>
        <p>The requested advisor event is missing or the id is invalid.</p>
        <Link href="/admin/sidecar">Back to sidecar dashboard</Link>
      </div>
    );
  }

  const advisorOutput = parseAdvisorOutput(event.advisor_output);
  const defaultActor = process.env.SIDECAR_DEFAULT_RATER || os.userInfo().username || 'operator';

  return (
    <div style={{ padding: 24, display: 'grid', gap: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'baseline' }}>
        <div>
          <h1 style={{ margin: 0 }}>Sidecar event #{event.id}</h1>
          <p style={{ margin: '8px 0 0', color: '#55616d' }}>
            {event.event_type} from {event.source} at {event.created_at}
          </p>
        </div>
        <Link href="/admin/sidecar">Back to sidecar dashboard</Link>
      </div>

      <section style={{ padding: 20, border: '1px solid #d7dde5', borderRadius: 16, background: '#fbfcfd' }}>
        <h2 style={{ marginTop: 0 }}>Event metadata</h2>
        <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '10px 16px', margin: 0 }}>
          <dt>Model</dt>
          <dd style={{ margin: 0 }}>{event.model_used || 'unknown'}</dd>
          <dt>Policy version</dt>
          <dd style={{ margin: 0 }}>{event.policy_version || 'unset'}</dd>
          <dt>Duration</dt>
          <dd style={{ margin: 0 }}>{event.duration_s ?? 0}s</dd>
          <dt>Rating</dt>
          <dd style={{ margin: 0 }}>{event.user_rating || 'unrated'}</dd>
          <dt>Rated at</dt>
          <dd style={{ margin: 0 }}>{event.rated_at || 'not rated yet'}</dd>
          <dt>Rated by</dt>
          <dd style={{ margin: 0 }}>{event.rated_by || 'not recorded'}</dd>
        </dl>
      </section>

      <section style={{ padding: 20, border: '1px solid #d7dde5', borderRadius: 16, background: '#fbfcfd' }}>
        <h2 style={{ marginTop: 0 }}>Captured content</h2>
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{event.content}</pre>
      </section>

      <section style={{ padding: 20, border: '1px solid #d7dde5', borderRadius: 16, background: '#fbfcfd' }}>
        <h2 style={{ marginTop: 0 }}>Advisor output</h2>
        {advisorOutput ? (
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {JSON.stringify(advisorOutput, null, 2)}
          </pre>
        ) : (
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {event.advisor_output_raw || event.advisor_output || 'No advisor output recorded.'}
          </pre>
        )}
      </section>

      <section style={{ padding: 20, border: '1px solid #d7dde5', borderRadius: 16, background: '#fbfcfd' }}>
        <h2 style={{ marginTop: 0 }}>Operator review</h2>
        <form
          action={`/api/v1/sidecar/events/${event.id}/rating`}
          method="post"
          style={{ display: 'grid', gap: 14, maxWidth: 720 }}
        >
          <label style={{ display: 'grid', gap: 6 }}>
            <span>Reviewer</span>
            <input
              type="text"
              name="rated_by"
              defaultValue={event.rated_by || defaultActor}
              style={{ padding: '10px 12px' }}
            />
          </label>
          <label style={{ display: 'grid', gap: 6 }}>
            <span>Notes</span>
            <textarea
              name="rating_notes"
              defaultValue={event.rating_notes || ''}
              rows={5}
              style={{ padding: '10px 12px', fontFamily: 'inherit' }}
            />
          </label>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button type="submit" name="rating" value="useful">
              Mark useful
            </button>
            <button type="submit" name="rating" value="not_useful">
              Mark not useful
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export const dynamic = 'force-dynamic';
