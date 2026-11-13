FROM python:3.12-slim
WORKDIR /app
COPY controller/app.py controller/decision.py /app/
COPY api /app/api
USER 65532:65532
ENTRYPOINT ["python", "/app/app.py"]
