"""Entrypoint для нового стека: `python -m app`."""

from __future__ import annotations

import uvicorn

from app.core.config import Config


def main() -> None:
    uvicorn.run("app.api:app", host="0.0.0.0", port=Config.PORT, factory=False)


if __name__ == "__main__":
    main()
