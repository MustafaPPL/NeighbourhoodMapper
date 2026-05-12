FROM eclipse-temurin:21-jdk-jammy

LABEL description="R5 Conveyal routing engine for London transit travel-time matrix"

ARG R5_VERSION=v7.2
ARG R5_JAR=r5-${R5_VERSION}-all.jar

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl wget \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /r5

RUN wget -q \
    "https://github.com/conveyal/r5/releases/download/${R5_VERSION}/${R5_JAR}" \
    -O r5.jar

RUN pip3 install --no-cache-dir pandas pyarrow requests

COPY run_transit_matrix.py /r5/run_transit_matrix.py

ENV R5_JAR=/r5/r5.jar
ENV DATA_DIR=/data
ENV OUTPUT_DIR=/output

ENTRYPOINT ["python3", "/r5/run_transit_matrix.py"]
