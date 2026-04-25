# Python Interview and System Design Prep

This document prepares an engineer for Python-focused backend interviews and system design discussions relevant to projects like this one.

## 1. Python language questions to expect

### Functions and decorators
- what is a decorator
- how does `functools.wraps` help
- what is a closure
- when would you use a callable object instead of a function

### Classes and object model
- difference between class method, static method, and instance method
- what is MRO
- composition vs inheritance
- what are common useful dunder methods

### Iteration and generators
- iterable vs iterator
- generator vs list
- benefits of lazy execution

### Context managers
- how `with` works
- why context managers matter
- synchronous vs asynchronous context managers

### Typing
- why use type hints in Python
- dataclass vs Pydantic
- when to use protocols

## 2. Async and concurrency questions to expect

- difference between concurrency and parallelism
- what the event loop does
- when to use async vs threads vs processes
- what the GIL is
- why blocking code inside async handlers is dangerous
- how cancellation and timeouts should be handled

## 3. Backend engineering questions to expect

- how would you structure a FastAPI service
- how do you design request/response schemas
- how do you model errors cleanly
- how do you implement retries safely
- what makes a workflow idempotent
- how do you instrument a backend with logs, metrics, and traces
- how do you design background workers safely

## 4. RAG and AI-backend questions to expect

- how do you design a chunking strategy
- what is token-aware chunking
- how do embeddings and vector search fit together
- what are pre-retrieval and post-retrieval steps
- how do you reduce hallucination risk
- how do you evaluate groundedness
- how do you observe and debug a RAG pipeline

## 5. MCP and workflow-system questions to expect

- what is the difference between decision logic and tool execution
- why use a governed tool boundary
- how do you handle degraded action paths
- how do you persist intent during dependency failure
- how do replay workers stay safe under duplicate retries
- how do you audit tool actions and operator actions

## 6. System design topics to prepare

### Service design
- monolith vs microservices
- sync vs async boundaries
- API gateway responsibilities
- service ownership and data ownership

### Reliability
- retries
- timeouts
- circuit breakers
- backpressure
- replay and recovery
- blast radius control

### Observability
- structured logging
- metrics
- tracing
- correlation IDs
- dashboards and alerts

### Governance
- auth and scope enforcement
- tenant isolation
- auditability
- PII handling
- HITL approval flows

## 7. Strong interview answers should include

- explicit tradeoffs
- failure-path behavior
- monitoring and debugging approach
- idempotency and duplication safety
- rollout and rollback thinking
- honest limits and residual risks

## 8. Example Python interview questions

### Language
- explain decorators with an example
- what problem do context managers solve
- explain `__getattr__` vs `__getattribute__`
- when would you use a generator instead of returning a list

### Async
- explain how `asyncio.gather` works
- what happens if a blocking call runs inside an async endpoint
- how would you limit concurrency for outgoing HTTP calls

### Backend
- how would you design a retry wrapper
- how would you make a webhook handler idempotent
- how would you structure a client wrapper around an external API

### Architecture
- design a RAG service
- design a replay worker
- design a governed tool execution system
- design observability for a multi-service backend

## 9. Example system design prompts

- design an enterprise RAG system with citations
- design a workflow system that degrades safely when downstream tools are unavailable
- design a replay mechanism for failed actions
- design a monitoring strategy for model calls, retrieval, and tool execution
- design a multi-tenant backend with auditability and PII controls

## 10. Good answer structure for system design

1. clarify scope and assumptions
2. define main actors and critical workflows
3. propose high-level architecture
4. define key data stores and contracts
5. explain failure handling
6. explain monitoring and ops visibility
7. explain security and governance
8. explain tradeoffs and rollout path

## 11. Python-specific red flags in interviews

- using threads for everything without understanding the GIL
- claiming async automatically makes code faster
- no distinction between validation errors and system errors
- no plan for retries, timeouts, or idempotency
- no observability story
- overusing metaclasses or clever language features where simple code would be clearer

## 12. What matters most for projects like this repo

If the interview or discussion resembles this repo’s architecture, the most important strengths are:

- async service design
- typed contracts
- resilient dependency wrappers
- replay-safe workflow design
- observability and traceability
- clear separation between agent logic, tool execution, and governance

## 13. Best prep priority order

1. Python async and concurrency
2. typing, Pydantic, and schema design
3. decorators and context managers
4. retries, timeouts, and circuit breakers
5. worker and replay patterns
6. RAG architecture
7. observability and monitoring
8. governance and auditability
