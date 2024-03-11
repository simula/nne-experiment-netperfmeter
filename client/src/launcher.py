#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =================================================================
#          #     #                 #     #
#          ##    #   ####   #####  ##    #  ######   #####
#          # #   #  #    #  #    # # #   #  #          #
#          #  #  #  #    #  #    # #  #  #  #####      #
#          #   # #  #    #  #####  #   # #  #          #
#          #    ##  #    #  #   #  #    ##  #          #
#          #     #   ####   #    # #     #  ######     #
#
#       ---   The NorNet Testbed for Multi-Homed Systems  ---
#                       https://www.nntb.no
# =================================================================
#
# Container-based Netperfmeter Launcher for NorNet Edge
#
# Copyright (C) 2024 by Hugo Martineau
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Contact: hugom@simula.no


import json
import logging
import logging.config
import os
import sys
import subprocess
import zmq

# path to the node id file
NODE_ID_FILE_PATH = "/nodeid"
# path to the config file
CONFIG_FILE_PATH = "/monroe/config"
# path to the log directory
LOG_DIRECTORY = "/monroe/results/log"
# set if roaming is authorized for roaming
IS_ROAMING_AUTHORIZED = False


# ====== Check node ID ======================================================
try:
    node_id_file = open(NODE_ID_FILE_PATH)
    node_id = int(node_id_file.read())
except:
    sys.stderr.write("Unable to read node ID from " + NODE_ID_FILE_PATH + "!\n")
    sys.exit(1)


# ====== Read configuration file ============================================
# try to open and load configuration file
try:
    config_file = open(CONFIG_FILE_PATH)
    configuration = json.load(config_file)
except:
    sys.stderr.write("Unable to read configuration from " + CONFIG_FILE_PATH + "!\n")
    sys.exit(1)
# try to read basic configuration
try:
    measurement_id = configuration["measurement_id"]
    mcc = configuration["mcc"]
    mnc = configuration["mnc"]
    # try to read extra ICCID
    try:
        iccid = configuration["iccid"]
    except:
        iccid = None
except Exception as e:
    sys.stderr.write(
        "Invalid or incomplete configuration in "
        + CONFIG_FILE_PATH
        + ":"
        + str(e)
        + "\n"
    )
    sys.exit(1)

# ====== Make sure the log directory exists =================================
try:
    os.makedirs(LOG_DIRECTORY, 0o755, True)
except:
    sys.stderr.write("ERROR: Unable to create directory " + LOG_DIRECTORY + "!\n")
    sys.exit(1)


# ====== Initialise logger ==================================================
LOGGING_CONF = {
    "version": 1,
    "handlers": {
        "default": {
            "level": "DEBUG",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "standard",
            "filename": LOG_DIRECTORY + "/netperfmeter_launcher.log",
            "when": "D",
        },
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [PID=%(process)d] %(message)s"
        },
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["default"],
    },
}
logging.config.dictConfig(LOGGING_CONF)
logging.debug("Starting")

if __name__ == "__main__":
    # ====== Initialise ZeroMQ metadata stream ==================================
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://172.17.0.1:5556")
    socket.setsockopt_string(zmq.SUBSCRIBE, "MONROE.META.DEVICE.MODEM")

    # ====== Start instances ====================================================
    processes = {}
    while True:
        topic = None
        metadata = None
        metadata_if = None
        metadata_imsi_mcc_mnc = None
        metadata_nw_mcc_mnc = None
        metadata_iccid = None
        metadata_mcc = None
        metadata_mnc = None
        # ------ Read metadata ---------------------------------------------------
        data = socket.recv().decode("utf-8").split(" ", 1)
        try:
            topic = data[0]
            metadata = json.loads(data[1])
        except Exception as e:
            logging.warning("WARNING: Cannot read metadata: %s \n", str(e))
        # ------ Extract ICCID and InterfaceName ---------------------------------
        if (topic is not None) and (metadata is not None):
            if topic.startswith("MONROE.META.DEVICE.MODEM") and topic.endswith(
                ".UPDATE"
            ):
                try:
                    metadata_if = metadata["InterfaceName"]
                    metadata_imsi_mcc_mnc = str(metadata["IMSIMCCMNC"])
                    metadata_nw_mcc_mnc = str(metadata["NWMCCMNC"])
                    metadata_iccid = str(metadata["ICCID"])
                    metadata_mcc = metadata_imsi_mcc_mnc[0:3]
                    metadata_mnc = metadata_imsi_mcc_mnc[3:]
                except Exception as e:
                    logging.warning(
                        "WARNING: Cannot read MONROE.META.DEVICE.MODEM: %s \n", str(e)
                    )
        # if metadataICCID is equal to iccid
        are_mcc_mnc_equal_to_metadata = mcc == metadata_mcc and mnc == metadata_mnc
        is_iccid_none_or_equal_to_metadata = (iccid == metadata_iccid) or (
            iccid is None
        )
        is_metadata_if_none = metadata_if is None
        if (
            are_mcc_mnc_equal_to_metadata
            and is_iccid_none_or_equal_to_metadata
            and not is_metadata_if_none
        ):
            # ------ Verify roaming ---------------------------------
            is_roaming = metadata_imsi_mcc_mnc != metadata_nw_mcc_mnc
            if is_roaming and not IS_ROAMING_AUTHORIZED:
                logging.error(
                    "Is roaming authorized is %s but metadata IMSI is %s and metadata network is %s !\n",
                    str(IS_ROAMING_AUTHORIZED),
                    str(metadata_imsi_mcc_mnc),
                    str(metadata_nw_mcc_mnc),
                )
                sys.exit(1)
            # ------ Verify existing process for same measurement id --
            # if there is an existing process with same iccid
            if measurement_id in processes:
                # if the process has terminated
                if processes[measurement_id].poll() is not None:
                    # remove the process
                    del processes[measurement_id]
                    logging.warning(
                        "WARNING: Instance for measurement ID %s has stopped!\n",
                        str(measurement_id),
                    )
            # if process does not exist
            if measurement_id not in processes:
                logging.debug(
                    "Starting instance %d on %s ..", measurement_id, metadata_if
                )
                cmd = [
                    "/opt/monroe/nne-experiment-netperfmeter/client/src/netperfmeter.py",
                    "--iface",
                    metadata_if,
                    "-id",
                    str(measurement_id),
                ]
                # create a new process
                processes[measurement_id] = subprocess.Popen(cmd)
                logging.debug("Started instance %d on %s ", measurement_id, metadata_if)
