# PATH: /vllm/Dockerfile



# =====================================================================
# MAIN SERVICE: vLLM SERVER
# =====================================================================
FROM nvidia/cuda:12.9.0-cudnn-devel-ubuntu24.04
VOLUME ["/model"]
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul
EXPOSE 8000



# =====================================================================
# COMMON PREPERATION
# =====================================================================
RUN apt-get update && apt-get install -y \
  nano curl wget iproute2 jq cron git \
  python3 python3-pip python3-venv

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN pip install --upgrade pip

# Install Latest stable vLLM
RUN VLLM_LATEST=$(pip index versions vllm | grep -oP 'vllm \(\K[^\)]+' | head -1) && \
    echo "Latest stable vllm version: $VLLM_LATEST" && \
    pip install "vllm==$VLLM_LATEST"

RUN echo 'PS1="\[\e[1;34m\]\$(date +\%H:\%M:\%S.\%3N)\[\e[90m\]|\[\e[1;33m\]\u\[\e[1;32m\]@\[\e[1;36m\]\w \[\e[0m\]> "' >> /root/.bashrc

# vLLM Environments
ENV HF_HOME=/model \
    HF_MODULES_CACHE=/tmp/hf_modules \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=all



# =====================================================================
# LAUNCH
# =====================================================================
RUN apt clean

RUN rm -rf /var/lib/apt/lists/*

ENTRYPOINT []

ARG MODEL_NAME="vLLM_model"
ENV VLLM_SERVED_MODEL_NAME=${MODEL_NAME}

CMD ["/bin/sh", "-c", "\
  GPU_COUNT=$(nvidia-smi -L | wc -l) && \
  echo \"1. GPU 갯수: $GPU_COUNT\" && \
  if [ \"$GPU_COUNT\" -lt 1 ]; then \
    echo \"❌ GPU가 없습니다. 실행을 중단합니다.\"; \
    exit 2; \
  fi && \
  echo \"2. vLLM을 실행합니다..\" && \
  python3 -m vllm.entrypoints.openai.api_server \
    --model /model \
    --served-model-name ${VLLM_SERVED_MODEL_NAME} \
    --host 0.0.0.0 \
    --trust_remote_code \
    --tensor-parallel-size $GPU_COUNT \
  && echo \"✅ vLLM이 잘 실행되고 있습니다.\""]
