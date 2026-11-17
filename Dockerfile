FROM python:3.12-slim

ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1

ARG TARGETARCH
ARG BREV_CLI_VERSION=0.6.337

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /root/.local/bin \
    && case "$TARGETARCH" in \
         amd64) checksum=99bf8383618903ab411a91605a43b2e2f5a333781860bd6743ba44bfc4920d4f ;; \
         arm64) checksum=dd0e5b009dfae81c31c1ea01971c115ffe3adbd183785854fb24510d7f9103e2 ;; \
         *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
       esac \
    && asset="brev-cli_${BREV_CLI_VERSION}_linux_${TARGETARCH}.tar.gz" \
    && curl -fsSL --retry 5 --retry-all-errors \
         "https://github.com/brevdev/brev-cli/releases/download/v${BREV_CLI_VERSION}/${asset}" \
         -o /tmp/brev-cli.tar.gz \
    && echo "$checksum  /tmp/brev-cli.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/brev-cli.tar.gz -C /root/.local/bin brev \
    && rm /tmp/brev-cli.tar.gz \
    && brev --version

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

CMD ["python", "-m", "stop_brev_gha_runner"]
