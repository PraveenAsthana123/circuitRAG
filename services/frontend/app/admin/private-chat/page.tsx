'use client';

/**
 * /admin/private-chat — page wrapper.
 *
 * 100% in-browser inference via WebLLM. Privacy contract is enforced
 * by drill_private_chat_webllm_page.py:
 *   - zero backend HTTP fetch (no network round-trip per inference)
 *   - model load is user-gated (not auto-load on mount; ~750 MB)
 *   - WebGPU detected before load attempt
 *
 * Per CLAUDE.md §47, §48, §49, §57.1.
 */

import WebLLMChat from './WebLLMChat';

export default function PrivateChatPage() {
  return (
    <main style={{ padding: 24 }}>
      <WebLLMChat />
    </main>
  );
}
