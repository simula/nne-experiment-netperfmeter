# ===== netperfmeter builder image =====
FROM crnaeng/base:core as netperfmeter_builder
# install netperfmeter build dependencies
RUN apt update && \
    apt install -y wget \
    cmake \
    g++ \
    bzip2 \
    xz-utils \
    libbz2-dev \
    libsctp-dev
# build netperfmeter
RUN cd /opt && \
    wget https://www.nntb.no/~dreibh/netperfmeter/download/netperfmeter-1.9.7.tar.xz && \
    tar -xvf netperfmeter-1.9.7.tar.xz && \
    cd /opt/netperfmeter-1.9.7 && \
    cmake . && \
    make
# ===== final image =====
FROM crnaeng/base:core
# install netperfmeter runtime dependencies
RUN apt update && \
    apt install -y libbz2-1.0 \
    libsctp1 \
    python3-netifaces \
    xz-utils
# copy netperfmeter binary from builder
COPY --from=netperfmeter_builder /opt/netperfmeter-1.9.7/src/netperfmeter /opt/netperfmeter
# create dir for src
RUN mkdir -p /opt/monroe/nne-experiment-netperfmeter/client/src
RUN mkdir -p /tmp/results
# copy src
COPY src /opt/monroe/nne-experiment-netperfmeter/client/src

ENTRYPOINT ["dumb-init", "--", "/usr/bin/python3", "/opt/monroe/nne-experiment-netperfmeter/client/src/launcher.py"]