FROM jenkins/jenkins:lts-jdk17
USER root

# Install Docker, kubectl, Helm, Python, and all dependencies in single layer
RUN curl https://get.docker.com > dockerinstall && chmod 777 dockerinstall && ./dockerinstall && \
    # Install kubectl
    curl -LO https://storage.googleapis.com/kubernetes-release/release/$(curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt)/bin/linux/amd64/kubectl && \
    chmod +x ./kubectl && \
    mv ./kubectl /usr/local/bin/kubectl && \
    # Install Helm
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash && \
    # Install Python and system dependencies
    apt-get update && apt-get install -y \
        python3 \
        python3-pip \
        jq \
        && rm -rf /var/lib/apt/lists/* && \
    # Install Python packages for Flink testing and Kafka validation
    # --break-system-packages is safe in Docker containers (PEP 668)
    # Using kafka-python-ng (maintained fork) for Python 3.13 compatibility
    pip3 install --no-cache-dir --break-system-packages \
        pytest==7.4.3 \
        kafka-python-ng==2.2.3 \
        python-dateutil==2.9.0 && \
    # Grant Docker socket access
    groupadd -f docker && \
    usermod -aG docker jenkins

# Install Jenkins plugins via environment variable (installed on first boot)
ENV JENKINS_PLUGINS="workflow-aggregator git configuration-as-code docker-workflow kubernetes-cli"

USER jenkins