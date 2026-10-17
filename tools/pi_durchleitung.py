"""Reicht die Transkription auf dem Pi unter http://127.0.0.1:<port> durch, für Browser, die der Hausstelle nicht
vertrauen (127.0.0.1 gilt als sicherer Ort, das Mikrofon geht also). Nach außen prüft die Durchleitung das Zertifikat
des Pi gegen die Hausstelle; durchgereicht werden rohe Bytes, also auch Ereignisströme, Bereiche und Hochladen.

Nutzung: python3 tools/pi_durchleitung.py [--port 8633] [--ziel 192.168.178.49:8631] [--hausstelle rootCA.pem]
"""

import argparse
import asyncio
import ssl
import subprocess
from pathlib import Path


def hausstelle() -> str:
    wurzel = subprocess.run(["mkcert", "-CAROOT"], capture_output=True, text=True, check=True).stdout.strip()
    return str(Path(wurzel) / "rootCA.pem")


async def leiten(lesen: asyncio.StreamReader, schreiben: asyncio.StreamWriter) -> None:
    try:
        while daten := await lesen.read(65536):
            schreiben.write(daten)
            await schreiben.drain()
    except (ConnectionError, ssl.SSLError):
        pass
    finally:
        schreiben.close()


async def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--port", type=int, default=8633)
    a.add_argument("--ziel", default="192.168.178.49:8631")
    a.add_argument("--hausstelle", default=None)
    args = a.parse_args()
    host, port = args.ziel.rsplit(":", 1)
    kontext = ssl.create_default_context(cafile=args.hausstelle or hausstelle())

    async def verbindung(lesen: asyncio.StreamReader, schreiben: asyncio.StreamWriter) -> None:
        try:
            z_lesen, z_schreiben = await asyncio.open_connection(host, int(port), ssl=kontext, server_hostname=host)
        except OSError:
            schreiben.close()
            return
        await asyncio.gather(leiten(lesen, z_schreiben), leiten(z_lesen, schreiben))

    server = await asyncio.start_server(verbindung, "127.0.0.1", args.port)
    print(f"http://127.0.0.1:{args.port} -> https://{args.ziel}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
