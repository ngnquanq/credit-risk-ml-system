FROM flink:1.17.1-scala_2.12-java11

# Install Python and PyFlink
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir pyflink==1.17.1

# Add Kafka SQL connector and format connectors for Flink Table API
ENV FLINK_HOME=/opt/flink
ENV FLINK_VERSION=1.17.1

# Copy the Kafka connector from local jars directory (already downloaded)
COPY jars/flink-sql-connector-kafka-${FLINK_VERSION}.jar ${FLINK_HOME}/lib/

# Add Debezium JSON format connector for CDC support
RUN curl -fsSL https://repo1.maven.org/maven2/org/apache/flink/flink-json/${FLINK_VERSION}/flink-json-${FLINK_VERSION}.jar \
    -o ${FLINK_HOME}/lib/flink-json-${FLINK_VERSION}.jar

# Add additional format connectors for robust CDC handling
RUN curl -fsSL https://repo1.maven.org/maven2/org/apache/flink/flink-connector-base/${FLINK_VERSION}/flink-connector-base-${FLINK_VERSION}.jar \
    -o ${FLINK_HOME}/lib/flink-connector-base-${FLINK_VERSION}.jar || true

# App code
WORKDIR /opt/app
COPY jobs/ /opt/app/jobs/

# Runtime configuration (overridable)
ENV KAFKA_BOOTSTRAP_SERVERS=broker:29092 \
    CDC_SOURCE_TOPIC=hc.applications.public.loan_applications \
    SINK_TOPIC_FEATURES=hc.application_features

# Submit the PyFlink job to the running session cluster
CMD ["bash", "-lc", "flink run -m flink-jobmanager:8081 -d -py /opt/app/jobs/cdc_application_etl.py -pyfs /opt/app/jobs"]
