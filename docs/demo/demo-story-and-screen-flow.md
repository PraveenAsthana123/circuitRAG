# Demo Story And Screen Flow

This document defines how to present the project from a demo and user-story point of view.

The goal is not only to show features.
The goal is to show:

- user value
- system intelligence
- graceful degradation
- operator control
- governance and auditability

That is the right enterprise demo posture for this repo.

## 1. Demo Principles

A strong demo for this project should:

- start from a user problem, not from infrastructure
- show a small number of screens
- make automatic system behavior visible
- show at least one failure or degraded path
- show operator or admin follow-through
- end with a clear business outcome

## 2. Recommended Demo Personas

Use one or more of these personas:

### Persona 1: HR manager

Needs:

- answers grounded in policy documents
- ability to trigger HR actions safely

### Persona 2: Support operator

Needs:

- visibility into queued or degraded actions
- ability to resolve or replay safely

### Persona 3: Compliance or platform reviewer

Needs:

- evidence of traceability
- audit visibility
- confidence that the system degrades safely

## 3. Best Demo Stories For This Repo

The strongest demo stories are:

1. grounded RAG answer
2. agentic action through MCP
3. failure and graceful degradation
4. recovery and replay

These four together show the real value of the system.

## 4. Demo Story 1 — Grounded Answer

### User story

An HR manager uploads a policy document and asks a question about leave rules.

### Goal

Show that the system can:

- ingest enterprise documents
- retrieve relevant chunks
- answer with citations

### Screen flow

1. `Upload`
2. `Documents`
3. `Ask`

### Input

- policy document
- user question

### Process

Automatic:

- parse document
- chunk document
- generate embeddings
- index for retrieval
- retrieve relevant context
- generate answer
- attach citations

### Output

- answer
- citations
- visible document state

### What to emphasize in the demo

- answer is grounded
- citations are shown
- document lifecycle is visible

## 5. Demo Story 2 — Agentic Action Through MCP

### User story

A user asks the system to perform an action such as creating a leave request or opening a support item.

### Goal

Show that the system can:

- interpret action intent
- route to the correct MCP tool
- execute safely

### Screen flow

1. `Ask`
2. optional `Tools` or architecture explanation screen

### Input

- natural-language action request

### Process

Automatic:

- classify intent
- choose tool
- validate scope
- call MCP server
- interpret result
- return action outcome

### Output

- successful tool result
- visible action confirmation

### What to emphasize in the demo

- the system does more than chat
- action execution is bounded and structured
- MCP is the control-plane seam

## 6. Demo Story 3 — Failure And Graceful Degradation

### User story

A user attempts the same action when the downstream MCP server is unavailable.

### Goal

Show that the system fails safely instead of failing blindly.

### Screen flow

1. `Ask`
2. `Admin`

### Input

- natural-language action request during dependency outage

### Process

Automatic:

- attempt tool call
- breaker rejects or call fails
- create draft instead of hard failure
- record audit and degraded path

### Output

- degraded response
- draft reference
- operator visibility into pending action

### What to emphasize in the demo

- no silent failure
- no repeated hammering of the dependency
- user intent is preserved
- operator can follow up later

## 7. Demo Story 4 — Recovery And Replay

### User story

After the dependency recovers, the operator or worker replays the pending draft.

### Goal

Show enterprise recovery behavior and operator control.

### Screen flow

1. `Admin`
2. optional health or debug view

### Input

- pending draft
- recovered dependency

### Process

Manual or automatic:

- operator resolves draft
  or
- worker replays pending draft

Automatic:

- reattempt tool call
- update draft state
- record replay audit

### Output

- resolved or replayed draft
- audit trail
- visible operational recovery

### What to emphasize in the demo

- recovery is structured
- replay is auditable
- operator and automation both have a place

## 8. Screen Navigation Recommendation

For a short demo, use this navigation:

1. `Upload`
2. `Documents`
3. `Ask`
4. `Admin`

For a more technical follow-up, optionally add:

5. `Tools`
6. `System Design`

This gives both:

- user-facing flow
- architecture explanation

## 9. Manual Vs Automatic Flow

The demo should explicitly separate:

- what the user or operator does
- what the system does automatically

### Manual actions

- upload document
- ask question
- trigger action request
- inspect admin state
- resolve or replay draft

### Automatic actions

- parsing
- chunking
- embedding
- indexing
- retrieval
- reranking
- inference
- MCP tool call
- draft fallback
- replay worker execution
- audit and metrics emission

## 10. Input / Process / Output Template

Use this structure in every demo explanation:

### Input

- what the user provides

### Process

- what the system does automatically
- what the operator may do manually

### Output

- what the user or operator sees

This keeps the demo clear and repeatable.

## 11. Recommended Demo Script

### Step 1

Upload an HR or policy document.

Say:

“First, I’m adding enterprise content into the system so the answer path has something grounded to work from.”

### Step 2

Open `Documents`.

Say:

“Here we can see the document lifecycle and that the document is ready for retrieval.”

### Step 3

Open `Ask` and ask a policy question.

Say:

“Now I’m asking a business question. The system retrieves the right chunks and answers with citations.”

### Step 4

Ask for an action.

Say:

“Now I’m moving from information retrieval to action execution. The system routes through MCP instead of directly coupling the assistant to downstream systems.”

### Step 5

Demonstrate failure.

Say:

“If the downstream tool system is unavailable, we don’t lose the request and we don’t pretend it succeeded. The system degrades safely into a draft.”

### Step 6

Open `Admin`.

Say:

“Now the operator can see the pending action and manage recovery instead of guessing what happened.”

### Step 7

Replay or resolve after recovery.

Say:

“Once the dependency is healthy again, the system or operator can replay the action with an audit trail.”

## 12. What The Demo Must Make Visible

A good demo should visibly show:

- grounded answers
- action execution
- degraded fallback
- replay and recovery
- operator control
- auditability

If those are not visible, the repo is being undersold.

## 13. Common Demo Mistakes

- starting with architecture instead of user value
- showing too many screens
- not making automatic system behavior explicit
- hiding degraded or failure behavior
- never showing operator follow-through
- using chat-only framing for a system that is clearly more than chat

## 14. Best Demo Narrative

The strongest narrative for this repo is:

“DocuMind is not just a RAG assistant. It is an enterprise document and action platform that can answer grounded questions, trigger controlled actions, degrade safely when dependencies fail, and recover with operator-visible replay and audit.”

That is the story the demo should tell.
