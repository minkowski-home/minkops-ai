"""Forward 127.0.0.1:PORT inside WSL 2 to TallyPrime on the Windows host.

The companion's native adapters address Tally at 127.0.0.1, as they do on the
user's PC. When developing in WSL, Tally runs on the Windows side, reachable
at the default gateway. This development-only relay lets the same adapter
code, rehearsal scripts and headless companion reach it unchanged:

  python scripts/wsl_tally_forward.py [--port 9000] [--host WINDOWS_HOST]

Connections are relayed byte for byte; Tally still serves one request at a
time, so callers must keep their own requests sequential.
"""

import argparse
import asyncio
import subprocess


def windows_host():
    route = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, check=True).stdout
    return route.split()[2]


async def relay(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


async def serve(port, host):
    async def connect(client_reader, client_writer):
        try:
            tally_reader, tally_writer = await asyncio.open_connection(host, port)
        except OSError:
            client_writer.close()
            return
        await asyncio.gather(relay(client_reader, tally_writer), relay(tally_reader, client_writer),
                             return_exceptions=True)

    server = await asyncio.start_server(connect, "127.0.0.1", port)
    print(f"Relaying 127.0.0.1:{port} -> {host}:{port}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host")
    args = parser.parse_args()
    asyncio.run(serve(args.port, args.host or windows_host()))
