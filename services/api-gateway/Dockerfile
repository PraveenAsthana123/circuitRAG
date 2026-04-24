# syntax=docker/dockerfile:1.7
FROM golang:1.22-alpine AS builder
WORKDIR /build
RUN apk add --no-cache git
COPY services/api-gateway/go.mod services/api-gateway/go.sum* ./
RUN go mod download 2>/dev/null || true
COPY services/api-gateway/ ./
# Re-resolve after sources arrive (in case go.sum wasn't committed yet)
RUN go mod tidy
ENV CGO_ENABLED=0 GOOS=linux
RUN go build -trimpath -ldflags="-s -w" -o /out/api-gateway ./cmd

FROM alpine:3.20 AS runtime
RUN apk add --no-cache ca-certificates curl && addgroup -g 10001 documind && adduser -D -u 10001 -G documind documind
COPY --from=builder /out/api-gateway /usr/local/bin/api-gateway
USER documind
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:${API_GATEWAY_HTTP_PORT:-8080}/healthz || exit 1
ENTRYPOINT ["/usr/local/bin/api-gateway"]
