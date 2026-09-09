# This local demo base uses a maintained tag; pin its digest for production.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BIND_ADDRESS=0.0.0.0
WORKDIR /app
# Copy only the runtime service, excluding tests, releases and operator state.
COPY --chown=10001:10001 app.py /app/app.py
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"
CMD ["python", "app.py"]
