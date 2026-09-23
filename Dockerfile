# Small, non-root image: Python + PyYAML (+ boto3 for the AWS connector).
FROM python:3.14-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.14-slim
LABEL org.opencontainers.image.title="AgentPosture" \
      org.opencontainers.image.description="Find every AI agent in your organization and know how risky each one is." \
      org.opencontainers.image.licenses="Apache-2.0"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)[aws]" && rm /tmp/*.whl \
 && useradd --system --uid 10001 --home /data agentposture && mkdir -p /data /config \
 && chown agentposture /data
USER agentposture
WORKDIR /data
EXPOSE 8484
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8484/healthz'); sys.exit(0)"
ENTRYPOINT ["agentposture"]
CMD ["-c", "/config/agentposture.yaml", "serve", "--host", "0.0.0.0"]
