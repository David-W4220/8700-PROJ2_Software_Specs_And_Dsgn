"""Start the onboard host: wiring only, no logic (see contracts.md, "Additions")."""
from __future__ import annotations

import argparse
import threading
from datetime import datetime, timezone

from ssir.screens import StationScreens
from ssir.station.clock import StationClock
from ssir.station.command_handler import StationCommandHandler
from ssir.station.identity import StationIdentity
from ssir.station.onboard_store import OnboardStore
from ssir.station.sync_agent import SyncAgent, SyncTransport


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m ssir.station")
    parser.add_argument("--data", required=True, help="onboard store path")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    store = OnboardStore(args.data)
    clock = StationClock(system_time=lambda: datetime.now(timezone.utc))
    identity = StationIdentity(store)
    handler = StationCommandHandler(store, identity, clock)
    transport: SyncTransport = NotImplemented  # the K11 channel; not built in the skeleton
    agent = SyncAgent(store, clock, transport)
    screens = StationScreens(handler, store, clock)

    stop = threading.Event()
    store.open()
    threading.Thread(target=agent.run, args=(stop,), daemon=True).start()
    screens.serve(args.host, args.port, stop)


if __name__ == "__main__":
    main()
