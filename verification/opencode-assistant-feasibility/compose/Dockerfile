# Minimal image for the OpenCode privacy/network verification only.
# The binary is copied from the developer host at build time; the build context
# is a scratch directory that contains nothing but the binary (see verify.sh).
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY opencode /usr/local/bin/opencode
RUN chmod +x /usr/local/bin/opencode

# A sandbox Location that contains only the verification profile.
RUN mkdir -p /sandbox
COPY opencode.json /sandbox/opencode.json
COPY plugins /sandbox/.opencode/plugins

WORKDIR /sandbox
ENV OPENCODE_DISABLE_MODELS_FETCH=1 \
    OPENCODE_DISABLE_AUTOUPDATE=1 \
    OPENCODE_DISABLE_PROJECT_CONFIG=0 \
    OPENCODE_PASSWORD=container-verify-password \
    MOCK_API_KEY=container-verify-secret \
    ARCHVERIFY_MOCK_URL=http://127.0.0.1:1/v1 \
    ARCHVERIFY_SANDBOX=/sandbox \
    XDG_CONFIG_HOME=/sandbox/.xdg/config \
    XDG_DATA_HOME=/sandbox/.xdg/data \
    XDG_CACHE_HOME=/sandbox/.xdg/cache \
    XDG_STATE_HOME=/sandbox/.xdg/state

EXPOSE 4096
CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
