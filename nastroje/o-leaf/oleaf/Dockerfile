FROM node:22-bookworm-slim

ARG BUILD_VERSION=0.8.0
ARG BUILD_ARCH=amd64

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="O-Leaf" \
  org.opencontainers.image.description="Offline LaTeX editor for Home Assistant"

ENV NODE_ENV=production \
    PORT=8099 \
    OLEAF_CONFIG_DIR=/config \
    OLEAF_RUNTIME_DIR=/data

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      biber \
      ca-certificates \
      fonts-dejavu \
      latexmk \
      poppler-utils \
      texlive-bibtex-extra \
      texlive-fonts-recommended \
      texlive-lang-czechslovak \
      texlive-latex-extra \
      texlive-science \
      texlive-xetex \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm ci --omit=dev \
    && mkdir -p public/vendor/codemirror/mode/stex public/vendor/codemirror/theme \
    && cp node_modules/codemirror/lib/codemirror.css public/vendor/codemirror/ \
    && cp node_modules/codemirror/lib/codemirror.js public/vendor/codemirror/ \
    && cp node_modules/codemirror/mode/stex/stex.js public/vendor/codemirror/mode/stex/ \
    && cp node_modules/codemirror/theme/material-darker.css public/vendor/codemirror/theme/

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod 0755 /run.sh

EXPOSE 8099
CMD ["/run.sh"]

