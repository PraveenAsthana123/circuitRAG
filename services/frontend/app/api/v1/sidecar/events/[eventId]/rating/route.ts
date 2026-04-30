import { NextRequest, NextResponse } from 'next/server';

import { rateSidecarEvent } from '../../../../../../../lib/sidecar';

type RouteParams = {
  params: {
    eventId: string;
  };
};

function redirectWithStatus(req: NextRequest, state: 'saved' | 'missing' | 'invalid' | 'failed') {
  const url = new URL('/admin/sidecar', req.url);
  url.searchParams.set('rating', state);
  url.hash = 'live-ratings';
  return NextResponse.redirect(url, { status: 303 });
}

export async function GET(req: NextRequest, { params }: RouteParams) {
  const eventId = Number(params.eventId);
  if (!Number.isInteger(eventId) || eventId <= 0) {
    return redirectWithStatus(req, 'invalid');
  }
  const url = new URL(`/admin/sidecar/${eventId}`, req.url);
  return NextResponse.redirect(url, { status: 303 });
}

export async function POST(req: NextRequest, { params }: RouteParams) {
  const eventId = Number(params.eventId);
  if (!Number.isInteger(eventId) || eventId <= 0) {
    return redirectWithStatus(req, 'invalid');
  }

  const form = await req.formData();
  const rating = String(form.get('rating') || '');
  if (rating !== 'useful' && rating !== 'not_useful') {
    return redirectWithStatus(req, 'invalid');
  }
  const ratedBy = String(form.get('rated_by') || '').trim();
  const ratingNotes = String(form.get('rating_notes') || '').trim();

  try {
    const saved = await rateSidecarEvent(eventId, rating, { ratedBy, ratingNotes });
    return redirectWithStatus(req, saved ? 'saved' : 'missing');
  } catch {
    return redirectWithStatus(req, 'failed');
  }
}

export const dynamic = 'force-dynamic';
