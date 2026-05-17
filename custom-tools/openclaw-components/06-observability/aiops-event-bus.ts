import { AIOpsEvent } from "./types";

export class AIOpsEventBus {
  publish(event: AIOpsEvent): void {
    console.log(JSON.stringify({
      type: "aiops_event",
      ...event,
    }));
  }
}
