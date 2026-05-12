FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    PORT=8000

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install -r requirements.txt

COPY app.py ./
COPY project_paths.py ./
COPY .streamlit ./.streamlit
COPY docs ./docs
COPY scripts ./scripts
COPY data ./data
COPY webapp ./webapp

EXPOSE 8000

CMD ["sh", "scripts/deployment/startup.sh"]
