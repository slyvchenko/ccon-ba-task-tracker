FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
COPY . /srv/app
RUN groupadd --system --gid 10001 ccon \
    && useradd --system --uid 10001 --gid ccon --home /srv/app ccon \
    && mkdir -p /srv/runtime/data /srv/runtime/inbox /srv/runtime/logs \
    && chown -R ccon:ccon /srv/runtime
USER ccon
EXPOSE 8765
CMD ["python", "server.py", "--cloud", "--port", "8765", "--data-dir", "/srv/runtime"]
