import { spawn } from 'child_process';
import { randomUUID } from 'crypto';
import { existsSync } from 'fs';
import { appendFile, mkdir, mkdtemp, readFile, rm } from 'fs/promises';
import { NextRequest, NextResponse } from 'next/server';
import os from 'os';
import path from 'path';

const OPENAI_TTS_URL = 'https://api.openai.com/v1/audio/speech';
const DEFAULT_OPENAI_MODEL = process.env.OPENAI_TTS_MODEL || 'gpt-4o-mini-tts';
const DEFAULT_OPENAI_VOICE = process.env.OPENAI_TTS_VOICE || 'alloy';
const WORKDIR = process.cwd();
const REPO_ROOT = path.resolve(WORKDIR, '..', '..');
const DEFAULT_PIPER_DIR =
  existsSync(path.join(WORKDIR, '.runtime', 'piper'))
    ? path.join(WORKDIR, '.runtime', 'piper')
    : path.join(REPO_ROOT, '.runtime', 'piper');
const DEFAULT_PIPER_MODEL = path.join(DEFAULT_PIPER_DIR, 'en_US-lessac-medium.onnx');
const DEFAULT_PIPER_CONFIG = `${DEFAULT_PIPER_MODEL}.json`;
const DEFAULT_PIPER_PYTHON =
  existsSync(path.join(WORKDIR, '.venv-tts', 'bin', 'python'))
    ? path.join(WORKDIR, '.venv-tts', 'bin', 'python')
    : path.join(REPO_ROOT, '.venv-tts', 'bin', 'python');
const DEFAULT_KOKORO_DIR =
  existsSync(path.join(WORKDIR, '.runtime', 'kokoro'))
    ? path.join(WORKDIR, '.runtime', 'kokoro')
    : path.join(REPO_ROOT, '.runtime', 'kokoro');
const DEFAULT_KOKORO_MODEL = path.join(DEFAULT_KOKORO_DIR, 'kokoro-v1.0.onnx');
const DEFAULT_KOKORO_VOICES = path.join(DEFAULT_KOKORO_DIR, 'voices-v1.0.bin');
const PIPER_TTS_URL = process.env.PIPER_TTS_URL || '';
const PIPER_TTS_BIN = process.env.PIPER_TTS_BIN || 'piper';
const PIPER_TTS_PYTHON = process.env.PIPER_TTS_PYTHON || DEFAULT_PIPER_PYTHON;
const PIPER_MODEL_PATH = process.env.PIPER_MODEL_PATH || (existsSync(DEFAULT_PIPER_MODEL) ? DEFAULT_PIPER_MODEL : '');
const PIPER_CONFIG_PATH = process.env.PIPER_CONFIG_PATH || (existsSync(DEFAULT_PIPER_CONFIG) ? DEFAULT_PIPER_CONFIG : '');
const PIPER_DEFAULT_VOICE = process.env.PIPER_VOICE || 'en_US-lessac-medium';
const KOKORO_TTS_PYTHON = process.env.KOKORO_TTS_PYTHON || DEFAULT_PIPER_PYTHON;
const KOKORO_MODEL_PATH = process.env.KOKORO_MODEL_PATH || (existsSync(DEFAULT_KOKORO_MODEL) ? DEFAULT_KOKORO_MODEL : '');
const KOKORO_VOICES_PATH = process.env.KOKORO_VOICES_PATH || (existsSync(DEFAULT_KOKORO_VOICES) ? DEFAULT_KOKORO_VOICES : '');
const KOKORO_DEFAULT_VOICE = process.env.KOKORO_VOICE || 'af_heart';
const KOKORO_DEFAULT_LANG = process.env.KOKORO_LANG || 'en-us';
const PIPER_SPEAKER = process.env.PIPER_SPEAKER || '';
const PIPER_LENGTH_SCALE = process.env.PIPER_LENGTH_SCALE || '';
const PIPER_NOISE_SCALE = process.env.PIPER_NOISE_SCALE || '';
const PIPER_NOISE_W = process.env.PIPER_NOISE_W || '';
const MAX_TEXT_CHARS = 4_000;
const AUDIT_DIR = path.join(process.cwd(), '.runtime');
const AUDIT_FILE = path.join(AUDIT_DIR, 'tts-audit.jsonl');

type TtsFormat = 'mp3' | 'wav' | 'pcm';
type ProviderName = 'kokoro_local' | 'piper_http' | 'piper_local' | 'openai' | 'browser_speech_synthesis';

type TtsRequest = {
  text?: string;
  voice?: string;
  format?: TtsFormat;
  model?: string;
  instructions?: string;
};

type AuditRow = {
  id: string;
  observed_at: string;
  correlation_id: string;
  provider: string;
  model: string;
  voice: string;
  chars: number;
  format: string;
  status: 'provider_unavailable' | 'upstream_error' | 'ok';
  detail: string;
  failover_chain: string[];
};

type ProviderAttempt = {
  provider: ProviderName;
  detail: string;
};

type SynthesisResult = {
  provider: Exclude<ProviderName, 'browser_speech_synthesis'>;
  model: string;
  voice: string;
  format: TtsFormat;
  contentType: string;
  body: ArrayBuffer | ReadableStream<Uint8Array>;
};

function correlationId(req: NextRequest): string {
  return req.headers.get('x-correlation-id') || randomUUID();
}

function jsonError(
  status: number,
  errorCode: string,
  detail: string,
  correlation_id: string,
  extra: Record<string, unknown> = {},
) {
  return NextResponse.json(
    { error_code: errorCode, detail, correlation_id, ...extra },
    { status, headers: { 'X-Correlation-ID': correlation_id } },
  );
}

function contentTypeFor(format: string): string {
  if (format === 'wav') return 'audio/wav';
  if (format === 'pcm') return 'audio/pcm';
  return 'audio/mpeg';
}

function knownVoices(primary: ProviderName): string[] {
  if (primary === 'kokoro_local') {
    return [
      'af_alloy', 'af_aoede', 'af_bella', 'af_heart', 'af_jessica', 'af_kore', 'af_nicole', 'af_nova', 'af_river', 'af_sarah', 'af_sky',
      'am_adam', 'am_echo', 'am_eric', 'am_fenrir', 'am_liam', 'am_michael', 'am_onyx', 'am_puck', 'am_santa',
      'bf_alice', 'bf_emma', 'bf_isabella', 'bf_lily',
      'bm_daniel', 'bm_fable', 'bm_george', 'bm_lewis',
      'ef_dora', 'em_alex', 'em_santa',
      'ff_siwis', 'hf_alpha', 'hf_beta', 'hm_omega', 'hm_psi',
      'if_sara', 'im_nicola',
      'jf_alpha', 'jf_gongitsune', 'jf_nezumi', 'jf_tebukuro', 'jm_kumo',
      'pf_dora', 'pm_alex', 'pm_santa',
      'zf_xiaobei', 'zf_xiaoni', 'zf_xiaoxiao', 'zf_xiaoyi',
      'zm_yunjian', 'zm_yunxi', 'zm_yunxia', 'zm_yunyang',
    ];
  }
  if (primary.startsWith('piper')) {
    return [PIPER_DEFAULT_VOICE];
  }
  if (primary === 'openai') {
    return ['alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse'];
  }
  return [];
}

function configuredProviders(): ProviderName[] {
  const out: ProviderName[] = [];
  if (KOKORO_MODEL_PATH && KOKORO_VOICES_PATH) out.push('kokoro_local');
  if (PIPER_TTS_URL) out.push('piper_http');
  if (PIPER_MODEL_PATH) out.push('piper_local');
  if (process.env.OPENAI_API_KEY) out.push('openai');
  out.push('browser_speech_synthesis');
  return out;
}

function providerOrder(): ProviderName[] {
  const configured = configuredProviders();
  const requested = (process.env.TTS_PROVIDER_ORDER || 'kokoro_local,piper_http,piper_local,openai,browser_speech_synthesis')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean) as ProviderName[];
  const order: ProviderName[] = [];
  for (const provider of requested) {
    if (configured.includes(provider) && !order.includes(provider)) order.push(provider);
  }
  for (const provider of configured) {
    if (!order.includes(provider)) order.push(provider);
  }
  return order;
}

function primaryProvider(): ProviderName {
  return providerOrder()[0] || 'browser_speech_synthesis';
}

async function appendAudit(row: AuditRow) {
  await mkdir(AUDIT_DIR, { recursive: true });
  await appendFile(AUDIT_FILE, `${JSON.stringify(row)}\n`, 'utf8');
}

async function readAudits(limit = 20): Promise<AuditRow[]> {
  try {
    const raw = await readFile(AUDIT_FILE, 'utf8');
    return raw
      .trim()
      .split('\n')
      .filter(Boolean)
      .map((line) => JSON.parse(line) as AuditRow)
      .slice(-limit)
      .reverse();
  } catch {
    return [];
  }
}

async function synthesizeWithOpenAI(body: TtsRequest, text: string, format: TtsFormat): Promise<SynthesisResult> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error('OPENAI_API_KEY is not configured.');
  }
  const payload = {
    model: body.model || DEFAULT_OPENAI_MODEL,
    voice: body.voice || DEFAULT_OPENAI_VOICE,
    input: text,
    instructions: body.instructions,
    response_format: format,
  };
  const upstream = await fetch(OPENAI_TTS_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  if (!upstream.ok || !upstream.body) {
    let detail = `OpenAI TTS request failed with status ${upstream.status}.`;
    try {
      const err = await upstream.json();
      detail = err?.error?.message || detail;
    } catch {
      // keep generic detail
    }
    throw new Error(detail);
  }
  return {
    provider: 'openai',
    model: String(payload.model),
    voice: String(payload.voice),
    format,
    contentType: contentTypeFor(format),
    body: upstream.body,
  };
}

async function synthesizeWithPiperHttp(body: TtsRequest, text: string, format: TtsFormat): Promise<SynthesisResult> {
  if (!PIPER_TTS_URL) {
    throw new Error('PIPER_TTS_URL is not configured.');
  }
  const response = await fetch(PIPER_TTS_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      voice: body.voice || PIPER_DEFAULT_VOICE,
      format,
      model: body.model || path.basename(PIPER_MODEL_PATH || 'piper'),
      instructions: body.instructions,
      speaker: PIPER_SPEAKER || undefined,
      noise_scale: PIPER_NOISE_SCALE || undefined,
      length_scale: PIPER_LENGTH_SCALE || undefined,
      noise_w: PIPER_NOISE_W || undefined,
    }),
  });
  if (!response.ok || !response.body) {
    const detail = `Piper HTTP TTS failed with status ${response.status}.`;
    throw new Error(detail);
  }
  const contentType = response.headers.get('content-type') || 'audio/wav';
  return {
    provider: 'piper_http',
    model: body.model || path.basename(PIPER_MODEL_PATH || 'piper-http'),
    voice: body.voice || PIPER_DEFAULT_VOICE,
    format: contentType.includes('mpeg') ? 'mp3' : contentType.includes('pcm') ? 'pcm' : 'wav',
    contentType,
    body: response.body,
  };
}

async function synthesizeWithPiperLocal(body: TtsRequest, text: string, format: TtsFormat): Promise<SynthesisResult> {
  if (!PIPER_MODEL_PATH) {
    throw new Error('PIPER_MODEL_PATH is not configured.');
  }
  const tempDir = await mkdtemp(path.join(os.tmpdir(), 'documind-piper-'));
  const outputPath = path.join(tempDir, 'speech.wav');
  const args = ['--model', PIPER_MODEL_PATH, '--output_file', outputPath];
  if (PIPER_CONFIG_PATH) args.push('--config', PIPER_CONFIG_PATH);
  if (PIPER_SPEAKER) args.push('--speaker', PIPER_SPEAKER);
  if (PIPER_LENGTH_SCALE) args.push('--length_scale', PIPER_LENGTH_SCALE);
  if (PIPER_NOISE_SCALE) args.push('--noise_scale', PIPER_NOISE_SCALE);
  if (PIPER_NOISE_W) args.push('--noise_w', PIPER_NOISE_W);

  try {
    const stderrChunks: Buffer[] = [];
    await new Promise<void>((resolve, reject) => {
      const piperCommand = existsSync(PIPER_TTS_BIN) ? PIPER_TTS_BIN : '';
      const usePythonModule = !piperCommand && existsSync(PIPER_TTS_PYTHON);
      const child = usePythonModule
        ? spawn(PIPER_TTS_PYTHON, ['-m', 'piper', ...args], { stdio: ['pipe', 'ignore', 'pipe'] })
        : spawn(PIPER_TTS_BIN, args, { stdio: ['pipe', 'ignore', 'pipe'] });
      child.stderr.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));
      child.on('error', reject);
      child.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error(Buffer.concat(stderrChunks).toString('utf8') || `piper exited with code ${code}`));
      });
      child.stdin.write(text);
      child.stdin.end();
    });
    const finalPath = format === 'wav' ? outputPath : path.join(tempDir, `speech.${format}`);
    if (format !== 'wav') {
      const ffmpegArgs =
        format === 'mp3'
          ? ['-y', '-i', outputPath, '-codec:a', 'libmp3lame', '-q:a', '4', finalPath]
          : ['-y', '-i', outputPath, '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '22050', finalPath];
      await new Promise<void>((resolve, reject) => {
        const child = spawn('ffmpeg', ffmpegArgs, { stdio: ['ignore', 'ignore', 'pipe'] });
        const stderrChunks: Buffer[] = [];
        child.stderr.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));
        child.on('error', reject);
        child.on('close', (code) => {
          if (code === 0) resolve();
          else reject(new Error(Buffer.concat(stderrChunks).toString('utf8') || `ffmpeg exited with code ${code}`));
        });
      });
    }
    const bodyBuffer = await readFile(finalPath);
    return {
      provider: 'piper_local',
      model: path.basename(PIPER_MODEL_PATH),
      voice: body.voice || PIPER_DEFAULT_VOICE,
      format,
      contentType: contentTypeFor(format),
      body: bodyBuffer.buffer.slice(
        bodyBuffer.byteOffset,
        bodyBuffer.byteOffset + bodyBuffer.byteLength,
      ) as ArrayBuffer,
    };
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

async function synthesizeWithKokoroLocal(body: TtsRequest, text: string, format: TtsFormat): Promise<SynthesisResult> {
  if (!KOKORO_MODEL_PATH || !KOKORO_VOICES_PATH) {
    throw new Error('KOKORO_MODEL_PATH or KOKORO_VOICES_PATH is not configured.');
  }
  if (!existsSync(KOKORO_TTS_PYTHON)) {
    throw new Error(`Kokoro Python runtime not found at ${KOKORO_TTS_PYTHON}.`);
  }
  const tempDir = await mkdtemp(path.join(os.tmpdir(), 'documind-kokoro-'));
  const outputPath = path.join(tempDir, 'speech.wav');
  const script = `
from kokoro_onnx import Kokoro
import soundfile as sf
import sys
model_path, voices_path, voice, lang, output_path = sys.argv[1:6]
text = sys.stdin.read()
k = Kokoro(model_path, voices_path)
audio, sr = k.create(text, voice=voice, speed=1.0, lang=lang)
sf.write(output_path, audio, sr)
`;
  try {
    await new Promise<void>((resolve, reject) => {
      const child = spawn(
        KOKORO_TTS_PYTHON,
        ['-c', script, KOKORO_MODEL_PATH, KOKORO_VOICES_PATH, body.voice || KOKORO_DEFAULT_VOICE, KOKORO_DEFAULT_LANG, outputPath],
        { stdio: ['pipe', 'ignore', 'pipe'] },
      );
      const stderrChunks: Buffer[] = [];
      child.stderr.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));
      child.on('error', reject);
      child.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error(Buffer.concat(stderrChunks).toString('utf8') || `kokoro exited with code ${code}`));
      });
      child.stdin.write(text);
      child.stdin.end();
    });
    const finalPath = format === 'wav' ? outputPath : path.join(tempDir, `speech.${format}`);
    if (format !== 'wav') {
      const ffmpegArgs =
        format === 'mp3'
          ? ['-y', '-i', outputPath, '-codec:a', 'libmp3lame', '-q:a', '4', finalPath]
          : ['-y', '-i', outputPath, '-f', 's16le', '-acodec', 'pcm_s16le', '-ac', '1', '-ar', '24000', finalPath];
      await new Promise<void>((resolve, reject) => {
        const child = spawn('ffmpeg', ffmpegArgs, { stdio: ['ignore', 'ignore', 'pipe'] });
        const stderrChunks: Buffer[] = [];
        child.stderr.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));
        child.on('error', reject);
        child.on('close', (code) => {
          if (code === 0) resolve();
          else reject(new Error(Buffer.concat(stderrChunks).toString('utf8') || `ffmpeg exited with code ${code}`));
        });
      });
    }
    const bodyBuffer = await readFile(finalPath);
    return {
      provider: 'kokoro_local',
      model: path.basename(KOKORO_MODEL_PATH),
      voice: body.voice || KOKORO_DEFAULT_VOICE,
      format,
      contentType: contentTypeFor(format),
      body: bodyBuffer.buffer.slice(
        bodyBuffer.byteOffset,
        bodyBuffer.byteOffset + bodyBuffer.byteLength,
      ) as ArrayBuffer,
    };
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

export async function GET(req: NextRequest) {
  const cid = correlationId(req);
  if (req.nextUrl.searchParams.get('view') === 'audits') {
    const limit = Number(req.nextUrl.searchParams.get('limit') || 20);
    const audits = await readAudits(Number.isNaN(limit) ? 20 : Math.max(1, Math.min(limit, 100)));
    return NextResponse.json(
      { items: audits, total: audits.length, correlation_id: cid },
      { headers: { 'X-Correlation-ID': cid } },
    );
  }
  const providers = configuredProviders();
  const order = providerOrder();
  const primary = primaryProvider();
  const available = primary !== 'browser_speech_synthesis';
  return NextResponse.json(
    {
      provider: primary,
      configured: available,
      available,
      fallback: 'browser_speech_synthesis',
      providers,
      failover_chain: order,
      model:
        primary === 'openai'
          ? DEFAULT_OPENAI_MODEL
          : primary === 'kokoro_local'
            ? path.basename(KOKORO_MODEL_PATH || 'kokoro')
            : primary === 'piper_local'
              ? path.basename(PIPER_MODEL_PATH || 'piper')
              : primary === 'piper_http'
                ? path.basename(PIPER_MODEL_PATH || 'piper-http')
                : DEFAULT_OPENAI_MODEL,
      voice:
        primary === 'kokoro_local'
          ? KOKORO_DEFAULT_VOICE
          : primary.startsWith('piper')
            ? PIPER_DEFAULT_VOICE
            : DEFAULT_OPENAI_VOICE,
      voices: knownVoices(primary),
      supported_formats: ['mp3', 'wav', 'pcm'],
      correlation_id: cid,
      open_source_ready: providers.includes('kokoro_local') || providers.includes('piper_http') || providers.includes('piper_local'),
    },
    { headers: { 'X-Correlation-ID': cid } },
  );
}

export async function POST(req: NextRequest) {
  const cid = correlationId(req);
  const auditId = randomUUID();
  let body: TtsRequest;
  try {
    body = (await req.json()) as TtsRequest;
  } catch {
    return jsonError(400, 'INVALID_JSON', 'Request body must be valid JSON.', cid);
  }

  const text = (body.text || '').trim();
  if (!text) {
    return jsonError(422, 'VALIDATION_ERROR', '`text` is required.', cid);
  }
  if (text.length > MAX_TEXT_CHARS) {
    return jsonError(422, 'TEXT_TOO_LONG', `Text exceeds max length of ${MAX_TEXT_CHARS} characters.`, cid);
  }

  const format = body.format || 'mp3';
  if (!['mp3', 'wav', 'pcm'].includes(format)) {
    return jsonError(422, 'VALIDATION_ERROR', '`format` must be mp3, wav, or pcm.', cid);
  }

  const order = providerOrder();
  const attempts: ProviderAttempt[] = [];
  let result: SynthesisResult | null = null;

  for (const provider of order) {
    if (provider === 'browser_speech_synthesis') continue;
    try {
      if (provider === 'kokoro_local') {
        result = await synthesizeWithKokoroLocal(body, text, format);
      } else if (provider === 'piper_http') {
        result = await synthesizeWithPiperHttp(body, text, format);
      } else if (provider === 'piper_local') {
        result = await synthesizeWithPiperLocal(body, text, format);
      } else if (provider === 'openai') {
        result = await synthesizeWithOpenAI(body, text, format);
      }
      if (result) break;
    } catch (error) {
      attempts.push({
        provider,
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }

  if (!result) {
    const detail =
      attempts.length > 0
        ? attempts.map((attempt) => `${attempt.provider}: ${attempt.detail}`).join(' | ')
        : 'No server TTS provider is configured.';
    await appendAudit({
      id: auditId,
      observed_at: new Date().toISOString(),
      correlation_id: cid,
      provider: 'browser_speech_synthesis',
      model: DEFAULT_OPENAI_MODEL,
      voice: body.voice || DEFAULT_OPENAI_VOICE,
      chars: text.length,
      format,
      status: 'provider_unavailable',
      detail,
      failover_chain: order,
    });
    return jsonError(
      503,
      'TTS_PROVIDER_UNAVAILABLE',
      detail,
      cid,
      { fallback: 'browser_speech_synthesis', failover_chain: order, audit_id: auditId },
    );
  }

  await appendAudit({
    id: auditId,
    observed_at: new Date().toISOString(),
    correlation_id: cid,
    provider: result.provider,
    model: result.model,
    voice: result.voice,
    chars: text.length,
    format: result.format,
    status: 'ok',
    detail: `Audio synthesized successfully via ${result.provider}.`,
    failover_chain: order,
  });

  return new NextResponse(result.body, {
    status: 200,
    headers: {
      'Content-Type': result.contentType,
      'Cache-Control': 'no-store',
      'X-Correlation-ID': cid,
      'X-TTS-Provider': result.provider,
      'X-TTS-Model': result.model,
      'X-TTS-Voice': result.voice,
      'X-TTS-Input-Chars': String(text.length),
      'X-TTS-Failover-Chain': order.join(','),
      'X-TTS-Audit-Id': auditId,
    },
  });
}
