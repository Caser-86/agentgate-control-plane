"""Run the local API for Playwright without noisy Windows Proactor shutdown errors."""

import asyncio
import sys

import uvicorn


def _install_shutdown_handler(loop: asyncio.AbstractEventLoop) -> None:
    def handle_exception(
        current_loop: asyncio.AbstractEventLoop, context: dict[str, object]
    ) -> None:
        error = context.get("exception")
        if isinstance(error, ConnectionResetError) and getattr(error, "winerror", None) == 10054:
            return
        current_loop.default_exception_handler(context)

    loop.set_exception_handler(handle_exception)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python e2e_server.py <port>")
    config = uvicorn.Config(
        "app.main:app", host="127.0.0.1", port=int(sys.argv[1]), loop="asyncio"
    )
    server = uvicorn.Server(config)

    async def serve() -> None:
        _install_shutdown_handler(asyncio.get_running_loop())
        await server.serve()

    asyncio.run(serve())


if __name__ == "__main__":
    main()
