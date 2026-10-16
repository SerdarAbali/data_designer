# Restricted OpenCode runtime for the Architecture Assistant.
#
# Pinned to OpenCode v2.0.30 via the exact npm package version. The build fails
# if the installed binary does not report the pinned version, so a floating or
# drifted runtime cannot be deployed.
#
# The runtime is deliberately minimal:
#   * a sandbox containing only the restricted profile and the plugin;
#   * all XDG state under /data so the (sensitive) OpenCode data directory is a
#     single bounded volume that is never served or mounted elsewhere;
#   * no shell, no repository, no user-provided code.

FROM node:20-bookworm-slim

ARG OPENCODE_VERSION=2.0.30

RUN npm install --global "@opencode/cli@${OPENCODE_VERSION}" \
    && [ "$(opencode --version)" = "opencode v${OPENCODE_VERSION}" ] \
    && opencode --version

RUN mkdir -p /sandbox /data

COPY opencode.json /sandbox/opencode.json
COPY assistant-tools.json /sandbox/assistant-tools.json
COPY .opencode/plugins /sandbox/.opencode/plugins

WORKDIR /sandbox

ENV OPENCODE_DISABLE_MODELS_FETCH=1 \
    OPENCODE_DISABLE_AUTOUPDATE=1 \
    XDG_CONFIG_HOME=/data/xdg/config \
    XDG_DATA_HOME=/data/xdg/data \
    XDG_CACHE_HOME=/data/xdg/cache \
    XDG_STATE_HOME=/data/xdg/state

# Exposed only to the internal Compose network. No host port is ever published.
EXPOSE 4096

CMD ["opencode", "serve", "--hostname", "0.0.0.0", "--port", "4096"]
