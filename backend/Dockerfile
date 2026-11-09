FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Non-root: also required for RLIMIT_NPROC to stop strategy processes from forking.
RUN useradd --system --create-home --uid 10001 vault
USER vault

EXPOSE 8000
CMD ["./start.sh"]
