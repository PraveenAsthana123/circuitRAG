import { ToolRequest } from "./types";

export class ResponsibleAIGuard {
  validate(request: ToolRequest): void {
    const inputText = JSON.stringify(request.input).toLowerCase();

    const blockedPatterns = [
      "delete system file",
      "steal password",
      "bypass security",
      "disable audit",
    ];

    for (const pattern of blockedPatterns) {
      if (inputText.includes(pattern)) {
        throw new Error(`Responsible AI policy blocked tool call: ${pattern}`);
      }
    }
  }
}
