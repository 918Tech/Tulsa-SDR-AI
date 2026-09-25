# Tulsa SDR AI

Multi-RTL-SDR orchestration with physical/virtual receiver allocation, digital decoder adapters, Whisper transcription, event logging, and live mapping.

## Architecture

- Physical RTL-SDR discovery by index and serial.
- Virtual dongle seed sources for deterministic hardware-free testing.
- OP25 adapter for P25 metadata/decoded-audio workflows.
- External DSD-family adapter point for DMR.
- Talkgroup identity comes from decoder metadata; speech transcription is not treated as the authoritative talkgroup ID.
- Per-talkgroup audio/event archival and a Flask-SocketIO/Leaflet dashboard.
- Configurable 851-869 MHz project bounds.

Virtual dongles are synthetic test sources; they do not create RF reception. Live RF requires receiver hardware or another real IQ source. Encrypted traffic is not decrypted by this project.

## Setup

    bash scripts/bootstrap_ubuntu.sh
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install -r requirements.txt
    cp config.example.json config.json
    python generate_trunk_tsv.py
    python run.py

Then open http://127.0.0.1:5000.

OP25/GNU Radio and the selected DMR decoder are native external components; configure their paths/commands in config.json. The included frequency/talkgroup entries are seed configuration values and should be verified before operational use.
