/**
 * Admin route-level layout — adds a sticky download toolbar at the top
 * of every admin page. Reads the page's <h1 class="section-title"> for
 * the export filename and Word document title.
 *
 * Skips render gracefully when no section-title is on the page.
 */

import PageDownloadBar from '../../components/PageDownloadBar';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageDownloadBar />
      {children}
    </>
  );
}
