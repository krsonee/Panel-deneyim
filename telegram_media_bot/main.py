"""Entry point: loads config, builds the bot application, and starts polling.

Run with:  python main.py
(see README.md for full, step-by-step Turkish setup instructions)
"""

from __future__ import annotations

import asyncio
import logging

from bot.config import ConfigError, load_settings
from bot.loader import build_application
from bot.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)

    logger.info("Bot başlatılıyor...")
    app = await build_application(settings)

    try:
        await app.dispatcher.start_polling(app.bot)
    finally:
        logger.info("Bot durduruluyor, kaynaklar serbest bırakılıyor...")
        await app.db_connection.close()
        await app.bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except ConfigError as exc:
        # Configuration errors are expected user mistakes (missing .env
        # values) — print a clean message instead of a stack trace.
        logging.basicConfig(level=logging.ERROR)
        logging.error("Yapılandırma hatası: %s", exc)
        raise SystemExit(1) from exc
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
