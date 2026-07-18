FROM golang:1.24.8-alpine3.22@sha256:3d78beb141d98f42337f1252ecf2a5f20374109929a4c3f6817f9e4179cc0ae5 AS build

ARG MINIO_COMMIT
WORKDIR /src
RUN test -n "${MINIO_COMMIT}" && \
    wget --quiet "https://github.com/minio/minio/archive/${MINIO_COMMIT}.tar.gz" \
      --output-document=/tmp/minio.tar.gz && \
    tar --extract --gzip --file=/tmp/minio.tar.gz --strip-components=1 && \
    mkdir --parents /out && \
    CGO_ENABLED=0 GOOS=linux go build \
      -tags kqueue \
      -trimpath \
      -ldflags="-s -w" \
      -o /out/minio .

FROM alpine:3.22.5@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce

ARG MINIO_COMMIT
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="${MINIO_COMMIT}" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

RUN addgroup -S -g 10001 minio && \
    adduser -S -u 10001 -G minio -h /nonexistent minio && \
    mkdir --parents /data /licenses/minio && \
    chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /licenses/minio/LICENSE
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt

USER 10001:10001
EXPOSE 9000 9001
VOLUME ["/data"]
ENTRYPOINT ["minio"]
