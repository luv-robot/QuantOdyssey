FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts
COPY configs ./configs
COPY freqtrade_user_data ./freqtrade_user_data
COPY public ./public

RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install ".[dashboard,orchestration]" freqtrade

EXPOSE 8501

CMD ["streamlit", "run", "scripts/dashboard_streamlit.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.baseUrlPath=app"]
