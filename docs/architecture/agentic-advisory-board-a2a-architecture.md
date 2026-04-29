# Agentic Advisory Board + A2A Architecture

This note describes a controlled multi-agent system for tasks that require:

- execution
- review
- specialist advice
- bounded agent-to-agent coordination
- human approval for risky actions

It is not a "many agents talking freely" design.

The control plane is the important part.

## 1. Core idea

Use five role classes:

1. Manager
2. Worker
3. Reviewer
4. Advisory board
5. Orchestrator

Rule:

- workers do
- reviewers check
- advisors warn
- orchestrator decides

## 2. High-level architecture

```mermaid
flowchart TB
  U[User or upstream system]
  GW[API Gateway]
  ORCH[Orchestrator / State Machine]
  MGR[Manager / Planner Agent]
  W1[Worker Agent]
  W2[Worker Agent]
  REV[Reviewer Agent]
  SEC[Security Advisor]
  ARCH[Architecture Advisor]
  FIN[FinOps Advisor]
  HITL[Human Approval]
  MEM[(Task + Memory Store)]
  ART[(Artifact Store)]
  AUD[(Audit Log)]
  POL[(Policy Store)]
  TOOLS[Tools / MCP / APIs / DB / Code]

  U --> GW
  GW --> ORCH
  ORCH --> MGR
  MGR --> W1
  MGR --> W2
  W1 --> TOOLS
  W2 --> TOOLS
  W1 --> ART
  W2 --> ART
  ART --> REV
  REV --> ORCH
  ORCH --> SEC
  ORCH --> ARCH
  ORCH --> FIN
  SEC --> ORCH
  ARCH --> ORCH
  FIN --> ORCH
  ORCH --> HITL
  ORCH --> MEM
  ORCH --> AUD
  ORCH --> POL
  ORCH --> U
```

## 3. C4-style container view

```mermaid
flowchart LR
  subgraph Edge
    UI[Web UI / API Client]
    AGW[Gateway]
  end

  subgraph Control
    ORCH[Orchestrator Service]
    POLICY[Policy Engine]
    AUDIT[Audit Service]
  end

  subgraph AgentRuntime
    MANAGER[Manager Agent Runtime]
    WORKERS[Worker Pool]
    REVIEWER[Reviewer Runtime]
    BOARD[Advisor Pool]
  end

  subgraph State
    TASKS[(Task Store)]
    MEMORY[(Short-term Memory)]
    ARTIFACTS[(Artifact Store)]
  end

  subgraph Integrations
    MCP[MCP Servers]
    EXT[External APIs]
    CODE[Code / Repo / Build]
    DATA[DB / Search / Files]
  end

  UI --> AGW --> ORCH
  ORCH --> POLICY
  ORCH --> AUDIT
  ORCH --> MANAGER
  MANAGER --> WORKERS
  WORKERS --> REVIEWER
  ORCH --> BOARD
  ORCH --> TASKS
  ORCH --> MEMORY
  ORCH --> ARTIFACTS
  WORKERS --> MCP
  WORKERS --> EXT
  WORKERS --> CODE
  WORKERS --> DATA
```

## 4. Execution flow

```mermaid
flowchart TD
  A[Receive task] --> B[Classify task]
  B --> C[Create plan]
  C --> D[Assign worker]
  D --> E[Execute task]
  E --> F[Collect artifact]
  F --> G[Reviewer checks output]
  G --> H{High risk or low confidence?}
  H -->|no| I[Approve]
  H -->|yes| J[Send to advisory board]
  J --> K{Need human approval?}
  K -->|yes| L[Human approval]
  K -->|no| M[Orchestrator decision]
  L --> M
  M --> N{Retry or finalize?}
  N -->|retry| D
  N -->|finalize| O[Return final output]
```

## 5. Sequence diagram

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant O as Orchestrator
  participant M as Manager
  participant W as Worker
  participant R as Reviewer
  participant A as Advisory Board
  participant H as Human

  U->>O: submit task
  O->>M: classify + plan
  M-->>O: plan
  O->>W: execute assigned task
  W-->>O: artifact + confidence + risks
  O->>R: review artifact
  R-->>O: review result
  alt risky or low confidence
    O->>A: request specialist advice
    A-->>O: advice + objections
    alt requires human gate
      O->>H: approval request
      H-->>O: approve / reject / revise
    end
    O->>W: retry with constraints
  else acceptable
    O-->>U: final output
  end
```

## 6. Agent-to-agent message contract

Use structured messages only.

```json
{
  "task_id": "task_123",
  "message_id": "msg_456",
  "from_agent": "manager",
  "to_agent": "worker_code",
  "message_type": "work_request",
  "goal": "Implement tenant-safe cache invalidation",
  "input": {
    "files": ["libs/py/documind_core/cache.py"],
    "constraints": ["no breaking API changes", "must preserve audit fields"]
  },
  "confidence": 0.82,
  "risks": ["cache-key format drift"],
  "next_action": "return patch plus tests"
}
```

Recommended `message_type` values:

- `plan`
- `work_request`
- `work_result`
- `review_result`
- `advice`
- `approval_request`
- `approval_response`
- `reject`
- `retry`
- `final`

## 7. Role definitions

### Manager

Responsibilities:

- classify request
- build task plan
- split work into bounded subtasks
- assign correct worker type
- define success criteria

Should not:

- directly execute all work
- override policy

### Worker

Responsibilities:

- perform one bounded task
- call tools
- produce artifact
- report confidence and risks

Should not:

- silently redefine the task
- approve its own output

### Reviewer

Responsibilities:

- verify requirements
- detect regressions
- detect missing tests
- reject low-quality work

Should not:

- become the main executor

### Advisory board

Good advisor types:

- security
- architecture
- compliance
- FinOps
- data governance

Responsibilities:

- evaluate from one specialist lens
- return structured objections or conditions

Should not:

- execute the task unless explicitly re-tasked

### Orchestrator

Responsibilities:

- maintain state
- enforce max steps
- enforce budget and timeout
- enforce tool permissions
- decide approve / retry / escalate
- write audit trail

## 8. Required state stores

### Task store

Tracks:

- task status
- owner
- retry count
- timestamps
- final disposition

### Memory store

Tracks:

- working memory
- recent intermediate state
- prior decisions for this task

Keep this short-lived.

### Artifact store

Stores:

- plans
- code patches
- review outputs
- reports
- generated files

### Audit log

Stores:

- every agent transition
- tool calls
- approvals
- rejections
- policy decisions

### Policy store

Stores:

- role permissions
- tool allowlists
- approval thresholds
- escalation rules

## 9. Safety controls

Minimum controls:

- max iterations per task
- timeout per step
- token budget
- cost budget
- tool allowlist per role
- no unrestricted self-looping
- no self-approval
- mandatory HITL for destructive actions
- complete audit logging

## 10. Decision policy

Example policy:

```text
If confidence < 0.70 -> require review
If security-sensitive -> require security advisor
If cost impact high -> require FinOps advisor
If data mutation or production deploy -> require human approval
If retry count > 2 -> escalate or fail
```

## 11. Recommended MVP

Start with:

- 1 orchestrator
- 1 manager
- 1 worker
- 1 reviewer
- 1 security advisor
- optional human approval node

Do not start with 10 agents.

## 12. Failure modes

### Too many overlapping agents

Problem:

- duplicated work
- confusion
- noisy feedback

Fix:

- assign strict ownership

### Reviewer becomes executor

Problem:

- no independent quality gate

Fix:

- separate review-only phase

### Advisory board triggered on every task

Problem:

- latency explosion
- cost explosion

Fix:

- policy thresholds for when advisors are invoked

### No bounded execution

Problem:

- loops
- runaway token spend
- stalled tasks

Fix:

- state machine with explicit stop conditions

## 13. Best stack

For a practical implementation:

- FastAPI for API surface
- LangGraph or explicit state machine for orchestration
- Postgres/Redis for task + state
- MCP for tools and side effects
- OpenTelemetry for traces
- structured audit log for evidence

## 14. Interview answer

> I would build the agentic system as a controlled multi-agent workflow, not a free-form conversation between agents. A manager plans, workers execute bounded tasks, a reviewer checks output quality, advisory-board agents provide specialist risk review, and a state-machine orchestrator controls retries, budgets, tool permissions, approvals, and audit logging. That keeps the system useful, debuggable, and safe under production constraints.
