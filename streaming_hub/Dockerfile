ARG BUILD_FROM=ghcr.io/hassio-addons/base-python/amd64:19.0.0
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Copy root filesystem
COPY rootfs /

# Setup base packages (FFmpeg for media processing/remuxing, curl, certificates)
RUN \
    apk add --no-cache \
        ffmpeg \
        curl \
        ca-certificates

# Set up application workspace
WORKDIR /app

# Install Python requirements
COPY requirements.txt /app/requirements.txt
RUN \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy backend and frontend source code
COPY backend /app/backend
COPY frontend /app/frontend

# Ensure s6-overlay service scripts are executable
RUN \
    chmod a+x /etc/s6-overlay/s6-rc.d/streaming_hub/run \
    && chmod a+x /etc/s6-overlay/s6-rc.d/streaming_hub/finish

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="JMaroz" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Streaming Hub" \
    org.opencontainers.image.authors="JMaroz" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/JMaroz/ha-streaming-hub" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
