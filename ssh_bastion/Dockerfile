# PATH /ssh_bastion/Dockerfile



# =====================================================================
# MAIN SERVICE: SSH Bastion for tunneling
# =====================================================================
FROM ubuntu:latest
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Seoul
EXPOSE 50247



# =====================================================================
# COMMON PREPERATION
# =====================================================================
RUN DEBIAN_FRONTEND=noninteractive apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    cron curl jq nano openssh-server sudo wget && \
    rm -rf /var/lib/apt/lists/*



# =====================================================================
# SSH INSTALLATION
# =====================================================================
RUN mkdir /var/run/sshd

RUN useradd -m -s /bin/bash vllm_admin && \
    mkdir -p /home/vllm_admin/.ssh && \
    chown -R vllm_admin:vllm_admin /home/vllm_admin/.ssh && \
    chmod 700 /home/vllm_admin/.ssh \

RUN usermod -aG sudo vllm_admin && \
    echo 'vllm_admin ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/vllm_admin-nopasswd && \
    chmod 440 /etc/sudoers.d/vllm_admin-nopasswd \

RUN useradd -m -s /bin/bash vllm_service_user && \
    mkdir -p /home/vllm_service_user/.ssh && \
    chown -R vllm_service_user:vllm_service_user /home/vllm_service_user/.ssh && \
    chmod 700 /home/vllm_service_user/.ssh

RUN echo 'PS1="\[\e[1;34m\]\$(date +\%H:\%M:\%S.\%3N)\[\e[90m\]|\[\e[1;33m\]\u\[\e[1;32m\]@\[\e[1;36m\]\w \[\e[0m\]> "' >> /root/.bashrc
RUN echo 'PS1="\[\e[1;34m\]\$(date +\%H:\%M:\%S.\%3N)\[\e[90m\]|\[\e[1;33m\]\u\[\e[1;32m\]@\[\e[1;36m\]\w \[\e[0m\]> "' >> /home/vllm_admin/.bashrc
RUN echo 'PS1="\[\e[1;34m\]\$(date +\%H:\%M:\%S.\%3N)\[\e[90m\]|\[\e[1;33m\]\u\[\e[1;32m\]@\[\e[1;36m\]\w \[\e[0m\]> "' >> /home/vllm_service_user/.bashrc

COPY vllm_admin.pub /home/vllm_admin/.ssh/authorized_keys
COPY vllm_service_user.pub /home/vllm_service_user/.ssh/authorized_keys

RUN chown vllm_admin:vllm_admin /home/vllm_admin/.ssh/authorized_keys && \
    chmod 600 /home/vllm_admin/.ssh/authorized_keys
RUN chown vllm_service_user:vllm_service_user /home/vllm_service_user/.ssh/authorized_keys && \
    chmod 600 /home/vllm_service_user/.ssh/authorized_keys

RUN sed -i 's/#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#\?PermitEmptyPasswords .*/PermitEmptyPasswords no/' /etc/ssh/sshd_config && \
    sed -i 's/#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config && \
    echo "" >> /etc/ssh/sshd_config && \
    echo "# User specific configurations" >> /etc/ssh/sshd_config && \
    echo "Match User vllm_admin" >> /etc/ssh/sshd_config && \
    echo "  PermitOpen any" >> /etc/ssh/sshd_config && \
    echo "" >> /etc/ssh/sshd_config && \
    echo "Match User vllm_service_user" >> /etc/ssh/sshd_config && \
    echo "  ForceCommand /usr/sbin/nologin" >> /etc/ssh/sshd_config && \
    echo "  PermitOpen vllm_ollama_bridge:11434" >> /etc/ssh/sshd_config



# =====================================================================
# LAUNCH
# =====================================================================
RUN apt clean

RUN rm -rf /var/lib/apt/lists/*

ENTRYPOINT []

CMD ["/usr/sbin/sshd", "-D"]
