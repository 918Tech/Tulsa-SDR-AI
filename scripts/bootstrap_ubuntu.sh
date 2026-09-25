#!/usr/bin/env bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip rtl-sdr librtlsdr-dev libusb-1.0-0-dev libsndfile1 gnuradio gnuradio-dev cmake make g++ git pkg-config
echo "Base RTL-SDR/GNU Radio dependencies installed. Configure external OP25 and DMR decoder paths in config.json."
