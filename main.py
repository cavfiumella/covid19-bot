#!/usr/bin/python3.9

"""Run my Telegram BOT.

Basic usage:   python3.9 main.py <Telegram API token>
Help:          python3.9 [-h|--help] main.py"""


from _version import get_version
from helpers.bot import MyBot

from argparse import ArgumentParser
import logging
from logging import getLogger
from traceback import format_exc


LOGGER = getLogger(__name__)


def main(token: str, /):
    mybot = MyBot(token)


if __name__ == "__main__":

    parser = ArgumentParser()
    parser.add_argument("-t", "--token", type=str, help="Telegram API token")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-v", "--version", action="store_true")

    args = parser.parse_args()

    if args.version:
        print(f"Versione {get_version()}")
        exit(0)

    logging.basicConfig(
        format="%(asctime)s %(name)s: %(message)s",
        level=logging.DEBUG if args.debug else logging.INFO
    )

    if not args.token:
        parser.print_help()
        print("error: token is required to run the bot!")
        exit(1)

    try:
        main(args.token)
    except:
        LOGGER.error(format_exc())
