import { GuardrailResult } from "./types";

export class ApprovalGate {
  requiresHumanApproval(result: GuardrailResult): boolean {
    return result.decision === "review";
  }

  createApprovalTicket(result: GuardrailResult): string {
    const ticketId = crypto.randomUUID();

    console.log(JSON.stringify({
      type: "approval_ticket",
      ticketId,
      decision: result.decision,
      findings: result.findings,
      timestamp: new Date().toISOString(),
    }));

    return ticketId;
  }
}
