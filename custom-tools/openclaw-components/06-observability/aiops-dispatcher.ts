import { EventRecord, EventSink } from "./sinks";

export type AIOpsTopic = "aiops.events" | "aiops.incidents";

export interface AIOpsDispatchEnvelope {
  readonly topic: AIOpsTopic;
  readonly key: string;
  readonly record: EventRecord;
  readonly timestamp: string;
}

export interface AIOpsEventDispatcher {
  dispatch(envelope: AIOpsDispatchEnvelope): void;
}

export class SinkAIOpsEventDispatcher implements AIOpsEventDispatcher {
  constructor(private readonly sink: EventSink) {}

  dispatch(envelope: AIOpsDispatchEnvelope): void {
    this.sink.emit(envelope.record);
  }
}

export class InMemoryAIOpsEventDispatcher implements AIOpsEventDispatcher {
  private readonly envelopes: AIOpsDispatchEnvelope[] = [];

  constructor(private readonly maxEnvelopes: number = 10_000) {
    if (maxEnvelopes < 1) throw new Error("maxEnvelopes must be >= 1");
  }

  dispatch(envelope: AIOpsDispatchEnvelope): void {
    this.envelopes.push({
      ...envelope,
      record: { ...envelope.record },
    });
    while (this.envelopes.length > this.maxEnvelopes) this.envelopes.shift();
  }

  list(): AIOpsDispatchEnvelope[] {
    return this.envelopes.map((envelope) => ({
      ...envelope,
      record: { ...envelope.record },
    }));
  }

  size(): number {
    return this.envelopes.length;
  }

  clear(): void {
    this.envelopes.length = 0;
  }
}

export interface KafkaAIOpsProducer {
  send(input: {
    readonly topic: string;
    readonly messages: Array<{
      readonly key: string;
      readonly value: string;
    }>;
  }): void;
}

export class KafkaAIOpsEventDispatcher implements AIOpsEventDispatcher {
  constructor(private readonly producer: KafkaAIOpsProducer) {}

  dispatch(envelope: AIOpsDispatchEnvelope): void {
    this.producer.send({
      topic: envelope.topic,
      messages: [{
        key: envelope.key,
        value: JSON.stringify(envelope.record),
      }],
    });
  }
}

export interface WebhookAIOpsClient {
  post(input: {
    readonly topic: string;
    readonly key: string;
    readonly payload: EventRecord;
  }): void;
}

export class WebhookAIOpsEventDispatcher implements AIOpsEventDispatcher {
  constructor(private readonly client: WebhookAIOpsClient) {}

  dispatch(envelope: AIOpsDispatchEnvelope): void {
    this.client.post({
      topic: envelope.topic,
      key: envelope.key,
      payload: { ...envelope.record },
    });
  }
}
