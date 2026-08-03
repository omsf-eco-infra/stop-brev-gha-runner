FROM python:3.12-slim

ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && bash -c "$(curl -fsSL https://raw.githubusercontent.com/brevdev/brev-cli/main/bin/install-latest.sh)"

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .

CMD ["python", "-m", "stop_brev_gha_runner"]
