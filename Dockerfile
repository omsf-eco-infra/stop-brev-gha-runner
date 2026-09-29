FROM python:3.12-slim

ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1

ARG TARGETARCH
ARG BREV_CLI_VERSION=0.6.335

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /root/.local/bin \
    && case "$TARGETARCH" in \
         amd64) checksum=89d778e6f1e5e52495f3e0f10393f1666a1b16d180001b13faec6f906955e6f8 ;; \
         arm64) checksum=3efeaaf4e07d293403115b9d1e87bdc9c5277b26e1241edf3d4d7312e21bccb4 ;; \
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
