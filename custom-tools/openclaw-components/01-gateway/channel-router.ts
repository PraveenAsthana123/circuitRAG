// ⚠️ STUB — this file was named in Component 1's folder layout but
//     NO source code was provided. The implementation below is a
//     minimal placeholder to fill the named slot so other code that
//     imports it does not break. It is NOT derived from the operator's
//     source.
//
//     Replace with the real implementation when available.
//     See ../GAPS.md (Component 1 row + Source-fidelity notes).

import { ChannelType, UserMessage } from "./types";

export interface ChannelAdapter {
  readonly channel: ChannelType;
  normalize(rawPayload: unknown): UserMessage;
  send(userId: string, reply: string): Promise<void>;
}

/**
 * Minimal in-memory adapter registry. Real implementation would:
 *   - validate signatures (Slack signing secret, WhatsApp HMAC, etc.)
 *   - rate-limit per channel
 *   - propagate `request_id` baggage to the gateway
 *   - emit observability spans per inbound message
 */
export class ChannelRouter {
  private readonly adapters = new Map<ChannelType, ChannelAdapter>();

  register(adapter: ChannelAdapter): void {
    this.adapters.set(adapter.channel, adapter);
  }

  dispatch(channel: ChannelType, rawPayload: unknown): UserMessage {
    const adapter = this.adapters.get(channel);
    if (!adapter) {
      throw new Error(`No adapter registered for channel: ${channel}`);
    }
    return adapter.normalize(rawPayload);
  }

  async reply(channel: ChannelType, userId: string, reply: string): Promise<void> {
    const adapter = this.adapters.get(channel);
    if (!adapter) {
      throw new Error(`No adapter registered for channel: ${channel}`);
    }
    return adapter.send(userId, reply);
  }
}
