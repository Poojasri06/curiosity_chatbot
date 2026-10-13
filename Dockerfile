FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY widget widget
COPY data data
RUN useradd -r app && chown -R app /srv
USER app
EXPOSE 8000
# --proxy-headers: the host's HTTPS proxy sets the real visitor address, which the rate limits use.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
