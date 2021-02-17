"""Entry point to operate with Elasticpath Shop Bot."""
import logging

import telegram_bot


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    telegram_bot.start_bot()


if __name__ == '__main__':
    main()
