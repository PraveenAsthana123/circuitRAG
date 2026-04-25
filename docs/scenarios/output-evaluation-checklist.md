# Output Evaluation Checklist

This checklist is for evaluating generated outputs from LLM, RAG, agentic, MCP, and workflow-driven systems.

It is meant to help reviewers judge output quality in a structured way instead of relying on vague impressions like "looks good" or "feels wrong."

## 1. Correctness

Check whether:

- the output answers the actual request
- the output reflects the task intent correctly
- the output uses provided inputs correctly
- the output does not invent unsupported facts
- the output respects explicit constraints from the request

## 2. Relevance

Check whether:

- the output stays on topic
- the output avoids unrelated filler
- the most important result is prioritized
- the output matches the requested depth
- the output matches the requested format

## 3. Completeness

Check whether:

- all required parts of the task are covered
- required fields or sections are present
- the output does not stop too early
- explicitly requested edge cases are addressed
- the answer is not only partially useful while pretending to be complete

## 4. Faithfulness And Grounding

Check whether:

- claims are supported by retrieved or provided context
- the output does not contradict the source material
- citations, if present, support the actual claims
- summaries preserve source meaning
- uncertainty is expressed honestly when context is weak

## 5. Structured Output Validity

Check whether:

- the output matches the required schema
- required keys are present
- value types are correct
- no invalid extra fields are introduced when strict schema matters
- the output is parsable under the expected mode

## 6. Tool And Action Correctness

Check whether:

- the correct tool or path was chosen
- the correct arguments were used
- the tool result was interpreted correctly
- the output reflects the actual outcome
- no fake action completion is claimed

## 7. Safety And Policy

Check whether:

- unsafe content is avoided when policy requires it
- scope and access boundaries are respected
- sensitive data is not leaked
- refusal happens when required
- allowed content is not over-blocked unnecessarily

## 8. Style And UX

Check whether:

- the output is clear and readable
- the tone matches the request
- the response is concise when brevity was requested
- the response is detailed when depth was requested
- wording is not confusing or misleading

## 9. Robustness

Check whether:

- the output remains useful under ambiguous input
- malformed or partial input is handled safely
- partial context leads to bounded, honest output
- repeated runs are acceptably stable when determinism is expected
- truncation or context pressure does not create false certainty

## 10. Latency And Cost Tradeoff

Check whether:

- output quality remains acceptable under lower-latency settings
- output quality remains acceptable under lower-cost model or config settings
- response time is appropriate for the task complexity
- token or compute usage is proportional to the value of the result

## 11. RAG-Specific Checks

Check whether:

- good retrieval leads to grounded answers
- weak retrieval is surfaced honestly
- partial context still yields a bounded answer
- conflicting documents are handled carefully
- citation-heavy answers remain accurate
- truncated context does not cause hallucinated certainty

## 12. Agent / MCP / Workflow Checks

Check whether:

- degraded responses are honest about fallback behavior
- breaker-open or unavailable-tool situations are represented clearly
- draft creation is reported with the correct reference
- replay success is reflected accurately
- replay conflict is reported truthfully
- scope denial is reported without leaking internal details

## 13. Comparative Evaluation Scenarios

Use this checklist when comparing:

- prompt A versus prompt B
- model A versus model B
- retrieval strategy A versus B
- reranker A versus B
- structured prompt versus freeform prompt
- fallback model versus primary model

## 14. Failure Scenarios To Watch For

Watch for:

- empty output
- malformed structured output
- partially correct but misleading output
- confident hallucination
- citation mismatch
- correct style but wrong substance
- correct action summary but wrong actual system state

## 15. High-Value Minimum Evaluation Set

If time is limited, evaluate these first:

1. exact-task correctness
2. grounding and faithfulness
3. completeness
4. structured-output validity
5. tool or action correctness
6. safety and policy compliance
7. latency and cost acceptability
8. degraded or failure honesty

## 16. Reviewer Prompt

When manually reviewing output, ask:

- Did this actually solve the task?
- What claim here is unsupported?
- What important part is missing?
- Is the structure valid for downstream use?
- Did the system claim work was completed when it was not?
- Is any safety or access boundary violated?
- Is this answer useful enough for the latency and cost it incurred?
