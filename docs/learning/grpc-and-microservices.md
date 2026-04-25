# gRPC And Microservices

This note is a learning guide for two related topics:

- gRPC as an internal service communication contract
- microservices as a system decomposition strategy

These topics are often discussed together because gRPC is frequently used inside microservice systems, especially where:

- strong contracts matter
- internal latency matters
- code generation is useful
- service boundaries are stable enough to justify explicit schemas

## 1. What gRPC Is

gRPC is a remote procedure call framework built around:

- Protocol Buffers
- generated client and server code
- strongly typed schemas
- efficient binary transport
- request and streaming patterns

It is best understood as:

- a contract and transport system for service-to-service communication

It is not:

- a replacement for good service boundaries
- a replacement for error handling
- a replacement for observability

## 2. Core gRPC Concepts

### Protocol Buffers

Protocol Buffers define:

- messages
- services
- request and response shapes
- evolution rules for contracts

### Unary RPC

One request, one response.

Best for:

- standard internal APIs
- query or command-style operations

### Server streaming

One request, many responses from server.

Best for:

- logs
- progressive results
- large output streams

### Client streaming

Many requests, one final response.

Best for:

- batch uploads
- event ingestion

### Bidirectional streaming

Many requests and many responses.

Best for:

- interactive low-latency protocols
- long-lived agent or event channels

## 3. Why Teams Use gRPC

Main reasons:

- strong typed contracts
- better internal performance than many JSON-over-HTTP paths
- easier code generation
- explicit schema evolution
- better fit for internal service communication than browser-facing APIs

## 4. gRPC Trade-Offs

### Advantages

- contract-first development
- efficient payloads
- strong generated clients
- easier internal compatibility management

### Costs

- browser access is awkward without grpc-web or gateway translation
- debugging can feel less simple than plain HTTP
- schema management becomes part of daily development
- overuse can create “RPC soup” if service boundaries are weak

## 5. What Microservices Are

Microservices are a decomposition strategy where a system is split into smaller services that own:

- a clear responsibility
- their own deployable unit
- their own failure domain
- ideally their own data and contract boundaries

They are useful when:

- teams need clear ownership
- parts of the system scale differently
- different domains evolve at different speeds
- failure isolation matters

They are not automatically better than a modular monolith.

## 6. Microservice Design Questions

Before splitting services, ask:

- what responsibility does this service own?
- what state does it own?
- what contract does it expose?
- what failure mode does it isolate?
- what scaling reason justifies the split?

Bad reasons to split:

- because microservices look modern
- because every bounded topic got its own service too early
- because teams want “clean architecture” without operational cost awareness

## 7. gRPC Inside Microservices

gRPC fits microservices best when:

- internal APIs are contract-heavy
- browser clients do not call the services directly
- gateway or edge layers translate external HTTP to internal gRPC or internal service calls
- latency and type safety matter

Typical shape:

```text
Browser / external client
  -> API gateway (HTTP)
  -> internal services (gRPC)
```

## 8. What Still Matters Even With gRPC

Using gRPC does not remove the need for:

- auth propagation
- tenant propagation
- deadlines and timeouts
- retries
- circuit breakers
- observability
- compatibility discipline

These remain system-design concerns, not transport concerns.

## 9. Monitoring gRPC In Microservice Systems

At minimum, monitor:

- request count
- latency: p50, p95, p99
- error rate by method
- deadline exceeded rate
- retry rate
- saturation
- trace continuity across hops

And for microservices overall:

- service-to-service dependency map
- queue and backlog behavior
- deployment and rollback behavior
- per-service ownership and alerts

## 10. Main Failure Scenarios

Important failure scenarios include:

- incompatible protobuf change
- gateway contract drift
- timeout mismatch across hops
- retry storm across service boundaries
- missing auth or tenant propagation
- service dependency deadlock or cascade
- poor observability between services

## 11. Senior Engineering Mindset

A strong engineer asks:

- should this be a service at all?
- should this path use gRPC or plain HTTP?
- what does the contract look like after six versions?
- what happens under timeout, retry, and partial failure?
- can operators trace one request across services clearly?

## 12. Bottom Line

gRPC is useful when you want:

- strong internal contracts
- fast internal communication
- generated client and server bindings

Microservices are useful when you want:

- clear ownership
- scaling independence
- failure isolation

Neither one is valuable if the system still has weak boundaries, weak observability, or weak operational discipline.
