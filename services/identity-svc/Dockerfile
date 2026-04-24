# syntax=docker/dockerfile:1.7
FROM golang:1.22-alpine AS builder
WORKDIR /build
RUN apk add --no-cache git
COPY services/identity-svc/ ./
RUN go mod tidy
ENV CGO_ENABLED=0 GOOS=linux
RUN go build -trimpath -ldflags="-s -w" -o /out/identity-svc ./cmd

FROM alpine:3.20
RUN apk add --no-cache ca-certificates curl && addgroup -g 10001 documind && adduser -D -u 10001 -G documind documind
COPY --from=builder /out/identity-svc /usr/local/bin/identity-svc
USER documind
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:${IDENTITY_HTTP_PORT:-8081}/health || exit 1
ENTRYPOINT ["/usr/local/bin/identity-svc"]
