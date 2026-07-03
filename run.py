"""Launch the Jira Work Dashboard."""

import socket

import uvicorn

from app.config import get_settings


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    settings = get_settings()
    lan_ip = local_ip()

    print("\n  Jira Work Dashboard")
    print("  -------------------")
    print(f"  Local:   http://127.0.0.1:{settings.port}")
    print(f"  Network: http://{lan_ip}:{settings.port}")
    print("  Share the Network URL with teammates on the same Wi‑Fi/LAN.\n")

    if not settings.credentials_configured:
        print("  [!] Credentials not set — copy .env.example to .env first.\n")

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
