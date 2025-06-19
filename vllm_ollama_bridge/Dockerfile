# PATH: /vllm_ollama_bridge/Dockerfile



# =====================================================================
# MAIN SERVICE: vLLM to Ollama API SERVER
# =====================================================================
FROM python:3.13-slim
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul
EXPOSE 11434



# =====================================================================
# COMMON PREPERATION
# =====================================================================
WORKDIR /app
COPY vllm_ollama_bridge_server.py /app
RUN chmod +x /app/vllm_ollama_bridge_server.py

RUN apt-get update && apt-get install -y \
  nano curl wget iproute2 jq cron git \
  python3 python3-pip python3-venv

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install --upgrade pip

RUN pip install uvicorn fastapi httpx

RUN echo 'PS1="\[\e[1;34m\]\$(date +\%H:\%M:\%S.\%3N)\[\e[90m\]|\[\e[1;33m\]\u\[\e[1;32m\]@\[\e[1;36m\]\w \[\e[0m\]> "' >> /root/.bashrc



# =====================================================================
# LAUNCH
# =====================================================================
RUN apt clean

RUN rm -rf /var/lib/apt/lists/*

ENTRYPOINT []

CMD ["uvicorn", "vllm_ollama_bridge_server:app", "--host", "0.0.0.0", "--port", "11434"]
