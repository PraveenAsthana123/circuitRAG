import { redirect } from 'next/navigation';

// Root / redirects to /ask.
export default function Home() {
  redirect('/ask');
}
