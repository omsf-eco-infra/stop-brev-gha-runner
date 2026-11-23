FROM ghcr.io/prefix-dev/pixi:0.82.1-bookworm-slim

ENV PATH="/app/.pixi/envs/prod/bin:${PATH}" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . .
RUN pixi install --locked -e prod \
    && pixi clean cache --yes \
    && brev --version

CMD ["python", "-m", "stop_brev_gha_runner"]
