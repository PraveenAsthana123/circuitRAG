/**
 * Admin route-level layout — passthrough.
 *
 * The PageDownloadBar (download formats + 🔊 Read) is mounted in the
 * root layout (app/layout.tsx) so it covers every page in the app, not
 * just admin. Keeping this file as a passthrough so future admin-only
 * concerns can land here without restructuring.
 */

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
