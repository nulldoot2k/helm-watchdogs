FROM python:3.12-slim
WORKDIR /app
COPY key_service /app/key_service
RUN pip install --no-cache-dir --disable-pip-version-check -r /app/key_service/requirements.txt
RUN mkdir -p /var/lib/watchdogs && chown -R 65532:65532 /app /var/lib/watchdogs
USER 65532:65532
ENTRYPOINT ["python", "-m", "key_service.server"]
