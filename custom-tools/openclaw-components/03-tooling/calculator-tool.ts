import { ToolDefinition } from "./types";

class ArithmeticParser {
  private index = 0;

  constructor(private readonly input: string) {}

  parse(): number {
    const value = this.parseExpression();
    this.skipWhitespace();

    if (this.index !== this.input.length) {
      throw new Error("Invalid arithmetic expression");
    }

    if (!Number.isFinite(value)) {
      throw new Error("Arithmetic result is not finite");
    }

    return value;
  }

  private parseExpression(): number {
    let value = this.parseTerm();

    while (true) {
      this.skipWhitespace();
      const operator = this.peek();

      if (operator !== "+" && operator !== "-") return value;

      this.index += 1;
      const right = this.parseTerm();
      value = operator === "+" ? value + right : value - right;
    }
  }

  private parseTerm(): number {
    let value = this.parseFactor();

    while (true) {
      this.skipWhitespace();
      const operator = this.peek();

      if (operator !== "*" && operator !== "/") return value;

      this.index += 1;
      const right = this.parseFactor();
      value = operator === "*" ? value * right : value / right;
    }
  }

  private parseFactor(): number {
    this.skipWhitespace();
    const char = this.peek();

    if (char === "+" || char === "-") {
      this.index += 1;
      const value = this.parseFactor();
      return char === "-" ? -value : value;
    }

    if (char === "(") {
      this.index += 1;
      const value = this.parseExpression();
      this.skipWhitespace();

      if (this.peek() !== ")") {
        throw new Error("Invalid arithmetic expression");
      }

      this.index += 1;
      return value;
    }

    return this.parseNumber();
  }

  private parseNumber(): number {
    this.skipWhitespace();
    const start = this.index;

    while (/\d/.test(this.peek())) this.index += 1;

    if (this.peek() === ".") {
      this.index += 1;
      while (/\d/.test(this.peek())) this.index += 1;
    }

    if (start === this.index) {
      throw new Error("Invalid arithmetic expression");
    }

    const value = Number(this.input.slice(start, this.index));
    if (!Number.isFinite(value)) {
      throw new Error("Invalid arithmetic expression");
    }

    return value;
  }

  private skipWhitespace(): void {
    while (/\s/.test(this.peek())) this.index += 1;
  }

  private peek(): string {
    return this.input[this.index] ?? "";
  }
}

export const calculatorTool: ToolDefinition = {
  name: "calculator",
  description: "Performs safe arithmetic operations",
  riskLevel: "low",
  allowedRoles: ["user", "admin"],

  async execute(input) {
    const expression = String(input.expression ?? "");

    if (!/^[0-9+\-*/().\s]+$/.test(expression)) {
      throw new Error("Invalid arithmetic expression");
    }

    return {
      expression,
      result: new ArithmeticParser(expression).parse(),
    };
  },
};
