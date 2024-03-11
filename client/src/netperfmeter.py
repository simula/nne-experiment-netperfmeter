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
# Container-based Iperd for NorNet Edge
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


# Ubuntu/Debian dependencies:
# python3-netifaces python3-zmq

import argparse
import subprocess
import logging
import logging.config
import os
import signal
import sys
import time
import glob
import netifaces
import shutil
import pathlib
from datetime import datetime
from ipaddress import ip_address
from enum import Enum


# ###### Constants ##########################################################
# transport protocol constant
class TransportProtocol(Enum):
    """Class enum for available transport protocols"""

    TCP = "tcp"
    UDP = "udp"
    SCTP = "sctp"
    DCCP = "dccp"


# Waiting time before restarting on error (in s)
SLEEP_ON_ERROR = 300
# default netperfmeter destination
DEFAULT_DADDR = ip_address("185.196.88.34")
# default destination port
DEFAULT_DPORT = 15211
# default running time
DEFAULT_TIME = 5
# netperfmeter specification for traffic
DEFAULT_OUTGOING_FRAME_RATE = 30
DEFAULT_OUTGOING_FRAME_SIZE = 166666
DEFAULT_INCOMING_FRAME_RATE = 0
DEFAULT_INCOMING_FRAME_SIZE = 0
DEFAULT_TRANSPORT = TransportProtocol.UDP
# number of minutes to interval two measurements
DEFAULT_INTERVAL = 60 * 6
# file path constants
NODEID_FILE = "/nodeid"
LOG_DIRECTORY = "/monroe/results/log"
FINAL_RESULT_DIRECTORY = "/monroe/results"
TMP_RESULT_DIRECTORY = "/tmp/results"
NETPERFMETER_BINARY = "/opt/netperfmeter"
XZ_BINARY = "/usr/bin/xz"


# ###### Global variables ###################################################
RUNNING = True
COMPRESS = True


def signal_handler(signum, frame):
    """Signal handler catching signal"""
    global RUNNING
    RUNNING = False


def get_network_interface_ip_address(name: str, ip_version: int = 4) -> ip_address:
    """Get network interface IP address from name

    Args:
        name (str): name of the network interface
        ip_version (int): IP version in [4, 6]

    Returns:
        ip_address: IP address of the network interface
    """
    if ip_version not in [4, 6]:
        raise ValueError(
            f"ip_version {ip_version} is not within authorized values [4, 6]"
        )
    af = netifaces.AF_INET if ip_version == 4 else netifaces.AF_INET6
    return ip_address(netifaces.ifaddresses(name)[af][0]["addr"])


def safe_copy_file_to_dir(file_path: str, directory: str, keep_source: bool = False):
    """Safely copy file to directory from file path

    Args:
        tmp_res_file_path (str): path to the temporary file
    """
    # retrieve file path
    source = pathlib.Path(file_path)
    destination_path = f"{pathlib.Path(directory)}/{source.name}"
    tmp_file = f"{destination_path}.tmp"
    # copy file to final result directory with .tmp
    shutil.copy2(source, tmp_file)
    # change file name removing tmp
    shutil.move(tmp_file, destination_path)
    if not keep_source:
        os.remove(source)


if __name__ == "__main__":
    # ###### Main program #######################################################

    # ====== Handle arguments ===================================================
    ap = argparse.ArgumentParser(description="Netperfmeter for NorNet Edge")
    ap.add_argument(
        "-d",
        "--daddr",
        help="Destination address",
        type=int,
        default=DEFAULT_DADDR,
    )
    ap.add_argument(
        "-ofr",
        "--outgoing_frame_rate",
        help="Frame rate in /s",
        type=int,
        default=DEFAULT_OUTGOING_FRAME_RATE,
    )
    ap.add_argument(
        "-ofs",
        "--outgoing_frame_size",
        help="Frame size in B",
        type=int,
        default=DEFAULT_OUTGOING_FRAME_SIZE,
    )
    ap.add_argument("-I", "--iface", help="Interface name", type=str, required=True)
    ap.add_argument(
        "-i",
        "--interval",
        help="Time in minute for sleeping interval",
        type=int,
        default=DEFAULT_INTERVAL,
    )
    ap.add_argument(
        "-id",
        "--instance",
        help="Measurement instance ID",
        type=int,
        required=True,
    )
    ap.add_argument(
        "-p",
        "--dport",
        help="Destination port",
        type=int,
        default=DEFAULT_DPORT,
    )
    ap.add_argument(
        "-t",
        "--time",
        help="Time in seconds to transmit for",
        type=int,
        default=DEFAULT_TIME,
    )
    ap.add_argument(
        "-tp",
        "--transport_protocol",
        help="Transport protocol",
        type=TransportProtocol,
        default=DEFAULT_TRANSPORT,
        choices=list(TransportProtocol),
    )
    ap.add_argument(
        "-ifr",
        "--incoming_frame_rate",
        help="Frame rate in /s",
        type=int,
        default=DEFAULT_INCOMING_FRAME_RATE,
    )
    ap.add_argument(
        "-ifs",
        "--incoming_frame_size",
        help="Frame size in B",
        type=int,
        default=DEFAULT_INCOMING_FRAME_SIZE,
    )
    ap.add_argument(
        "-u",
        "--uncompressed",
        help="Turn off results compression",
        action="store_true",
        default=False,
    )
    # ====== Verify arguments value =============================================
    options = ap.parse_args()
    if (options.dport < 1) or (options.dport > 65535):
        sys.stderr.write(f"ERROR: Invalid destination port {options.dport}!\n")
        sys.exit(1)
    if (options.time < 0) or (options.time > 60):
        sys.stderr.write(f"ERROR: Invalid time {options.time}!\n")
        sys.exit(1)
    if options.interval < 0:
        sys.stderr.write(f"ERROR: Invalid interval {options.bitrate}!\n")
        sys.exit(1)
    if options.transport_protocol not in list(TransportProtocol):
        sys.stderr.write(
            f"ERROR: Invalid transport protocol {options.transport_protocol}!\n"
        )
        sys.exit(1)
    if options.uncompressed is True:
        COMPRESS = False
    # ====== Make sure the output directories exist =============================
    for directory in [LOG_DIRECTORY, FINAL_RESULT_DIRECTORY, TMP_RESULT_DIRECTORY]:
        try:
            os.makedirs(directory, 0o755, True)
        except Exception:
            sys.stderr.write("ERROR: Unable to create directory " + directory + "!\n")
            sys.exit(1)
    # ====== Initialise logger ==================================================
    LOGGING_CONF = {
        "version": 1,
        "handlers": {
            "default": {
                "level": "DEBUG",
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "standard",
                "filename": (LOG_DIRECTORY + "/netperfmeter_%d.log")
                % (options.instance),
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
    # ====== Initialise signal handlers ===============================
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    # ====== Main loop ==========================================================
    while RUNNING is True:
        try:
            # ----- Run experiments -------------------------------------------------
            # retrieve formatted now UTC datetime ISO8601
            utc_now_iso8601 = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            # retrieve network interface ip from name
            iface_ip = get_network_interface_ip_address(options.iface, 4)
            # netperfmeter cmd
            cmd = [
                NETPERFMETER_BINARY,
                f"{options.daddr}:{options.dport}",
                # generate file within the same folder
                f"-vector={TMP_RESULT_DIRECTORY}/netperfmeter_{options.instance}_vector_{utc_now_iso8601}.vec.bz2",
                f"-scalar={TMP_RESULT_DIRECTORY}/netperfmeter_{options.instance}_scalar_{utc_now_iso8601}.vec.bz2",
                "-control-over-tcp",
                f"-local={iface_ip}",
                f"-{options.transport_protocol.value}",
                f"const{options.outgoing_frame_rate}:const{options.outgoing_frame_size}:const{options.incoming_frame_rate}:const{options.incoming_frame_size}",
                f"-runtime={options.time}",
            ]
            logging.debug("Running %s", str(cmd))
            # instanciate netperfmeter and retrie output
            output = subprocess.check_output(cmd).decode("ascii")
            logging.debug("%s", str(output))
            # ----- Compress data ------------------------------------------------
            # for every data file
            for file_path in glob.glob(
                f"{TMP_RESULT_DIRECTORY}/netperfmeter_{options.instance}_*"
            ):
                # compress each file since wildcard not working in container
                cmd = [
                    XZ_BINARY,
                    "--compress",
                    file_path,
                ]
                # instanciate xz process
                subprocess.run(cmd, check=True)
            # ----- Copy compress data to directory  --------------------------------
            # for every compressed file
            for file_path in glob.glob(
                f"{TMP_RESULT_DIRECTORY}/netperfmeter_{options.instance}_*.xz"
            ):
                # safely copy compress file to final directory
                safe_copy_file_to_dir(file_path, FINAL_RESULT_DIRECTORY)
            logging.debug("Waiting %s minutes", str(options.interval))
            # sleep m minutes until next measurement
            time.sleep(options.interval * 60)

        # ====== Handle error ====================================================
        except Exception as e:
            logging.warning("Sleeping: %s", str(e))
            time.sleep(SLEEP_ON_ERROR)

    logging.debug("Exiting")
