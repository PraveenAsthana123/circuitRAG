# syntax=docker/dockerfile:1.7
FROM golang:1.22-alpine AS builder
WORKDIR /build
RUN apk add --no-cache git
COPY services/finops-svc/ ./
RUN go mod tidy
ENV CGO_ENABLED=0 GOOS=linux
RUN go build -trimpath -ldflags="-s -w" -o /out/finops-svc ./cmd

FROM alpine:3.20
RUN apk add --no-cache ca-certificates curl && addgroup -g 10001 documind && adduser -D -u 10001 -G documind documind
COPY --from=builder /out/finops-svc /usr/local/bin/finops-svc
USER documind
EXPOSE 8087
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:${FINOPS_HTTP_PORT:-8087}/health || exit 1
ENTRYPOINT ["/usr/local/bin/finops-svc"]
