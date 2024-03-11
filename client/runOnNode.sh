#!/bin/bash -e

# ==== Define constant variables =============================================
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONTAINER="netperfmeter"
CONTAINERTAG="crnaeng/netperfmeter:0.1"
TESTNAME="netperfmeter"
WORKDIR="/run/shm/${TESTNAME}"
# ==== Prepare workdir and configuration file ==
echo "Prepare:"
rm -rf $WORKDIR
mkdir -p $WORKDIR
echo '{"iccid": "8947080037110771036", "measurement_id": 99999, "mcc":"242", "mnc": "02"}' > $WORKDIR/config
mkdir -p $WORKDIR/results
# ==== Pull the newest docker image ==========================================
echo "Update:"
docker rm -f ${TESTNAME} >/dev/null 2>&1 || true
sudo docker pull ${CONTAINERTAG}
# ==== Instanciate the docker container ======================================
echo "Run:"
MONROE_NAMESPACE=$(docker ps --no-trunc -aqf name=monroe-namespace)
docker run --detach \
   --name ${TESTNAME} \
   --net=container:$MONROE_NAMESPACE \
   --cap-add NET_ADMIN \
   --cap-add NET_RAW \
   --shm-size=1G \
   -v $WORKDIR/results:/monroe/results \
   -v $WORKDIR/config:/monroe/config:ro \
   -v /etc/nodeid:/nodeid:ro \
   ${CONTAINERTAG}

sleep 1

docker exec --interactive --tty ${TESTNAME} /bin/bash