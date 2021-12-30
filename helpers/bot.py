
"""Telegram BOT sending Covid-19 updates."""


from .database import Report
from . import contagions, vaccines

from logging import getLogger, Logger
from typing import Dict, List, Tuple, Any, Optional, Union
from pathlib import Path
from telegram import (
    Update,
    Bot,
    Chat,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Updater,
    CallbackContext,
    CommandHandler,
    PicklePersistence,
    ConversationHandler,
    MessageHandler
)
from telegram.ext.filters import Filters
import pandas as pd
import numpy as np
from functools import partial
from threading import Thread
import threading
import time
import traceback


LOGGER = getLogger(__name__)


class MyBot:
    """This is my BOT.

    Logging:
      To discriminate operations done for different chats, logging for user
      actions is done using one Logger per chat.
    """

    # object logger
    _logger: Logger = None

    # databases objects
    _db: Dict[str, object] = None

    _updater: Updater = None

    # data files locations
    _data: Dict[str, Path] = {
        "dir": Path("share"),
        "msg": Path("share/msg"),
        "pkl": Path("share/bot.pkl")
    }

    # available commands; (command, description) pairs
    _commands_descriptions: Dict[str, str] = {
        "start": "messaggio di benvenuto",
        "help": "comandi disponibili e uso",
        "imposta_report": "attiva gli aggiornamenti",
        "disattiva_report": "disattiva gli aggiornamenti",
        "stato_report": "visualizza impostazioni",
        "bug": "segnala un errore",
        "feedback": "lascia un suggerimento"
    }

    # reports settings; values are (setting, available answers) pairs
    _report_settings: Dict[str, List[str]] = {
        "frequency": ["giornaliera", "settimanale", "mensile"],
        "contagions_national": ["Sì", "No"],
        "contagions_regional": None,
        "vaccines_national": ["Sì", "No"],
        "vaccines_regional": None
    }

    # correspondig datetime fmt for frquencies
    _frequency_fmt: Dict[str, str] = {
        "giornaliera": "%Y-%m-%d",
        "settimanale": "anno %Y, settimana %W",
        "mensile": "%Y-%m"
    }

    # offsets used to determine current period in report generation;
    # values are (frequency, days offset) pairs
    _frequency_offset: Dict[str, int] = {
        "giornaliera": 0,
        "settimanale": -7,
        "mensile": -30
    }

    # do not send reports in this hours
    _report_do_not_disturb: Tuple[str] = ("21:00", "10:00")

    _report_scheduler: Thread = None

    # variable to stop thread
    _stop_report_scheduler: bool = False


    def _get_chat_logger(self, chat_id: int, /) -> Logger:
        """Get Logger for chat."""

        return getLogger(f"{self}.chat_{chat_id}")


    def _send_message(
        self, chat_id: int, /, parse_mode: str = "html",
        path: Optional[Path] = None, text: Optional[str] = None,
        fmt: Optional[Tuple[Any]] = None, **kwargs
    ) -> None:
        """Send message.

        Parameters:
        - chat_id
        - parse_mode: telegram.Bot.send_message parse modes
        - path: file containing the message, if path is a file with extension
                \"*.md\" parse_mode is converted to \"MarkdownV2\"
        - text: text to send
        - fmt: call str.format on text message with this arguments
        - additional kwargs: passed to telegram.Bot.send_message

        One between path and text must be a valid argument, otherwise a
        ValueError is raised.
        """

        if path == None and text == None:
            raise ValueError("path and text are None")

        if path != None:
            with open(path) as file:
                text = file.read()

            if path.name.split(".")[-1] == "md":
                parse_mode = "MarkdownV2"

                self._get_chat_logger(chat_id).debug(
                    "Markdown file detected: parse_mode changed to "
                    f"\"{parse_mode}\""
                )

        if fmt != None:
            text = text.format(*fmt)

        self._updater.dispatcher.bot.send_message(
            chat_id=chat_id, parse_mode=parse_mode, text=text, **kwargs
        )

        self._get_chat_logger(chat_id).debug(
            f"Sent message: parse_mode = \"{parse_mode}\", text = \"{text}\""
        )


    def _start(self, update: Update, context: CallbackContext) -> None:
        """/start command.
        Send a welcome message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).info(
            f"User @{user.username} (id: {user.id}, chat id: {chat.id}) starts "
            "the bot"
        )

        self._get_chat_logger(chat.id).debug("/start command")

        if user.first_name != None and user.first_name != "":
            fmt = (user.first_name,)
        else:
            # fallback
            fmt = (user.username,)

        self._send_message(
            chat.id, path=self._data["msg"].joinpath("start.md"), fmt=fmt
        )


    def _help(self, update: Update, context: CallbackContext) -> None:
        """/help command.
        Send help message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug("/help command")

        text = "I comandi disponibili sono:\n\n"

        for command, description in self._commands_descriptions.items():
            text += f"- /{command}: {description}\n"

        self._send_message(chat.id, text=text)


    def _set_reports(
        self, update: Update, context: CallbackContext,
        setting: Optional[str] = None
    ) -> Union[str,int]:
        """/imposta_report command.
        Conversate with user to set reports.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug(
            f"/imposta_report command, setting = \"{setting}\""
        )

        # conversation starts, store current configuration to restore it later
        # if needed
        if setting == None:
            previous = context.chat_data.copy()
            context.chat_data.clear()
            context.chat_data.update({"previous_settings": previous})

            self._get_chat_logger(chat.id).debug(
                "Previous settings: "
                f"{context.chat_data.get('previous_settings')}"
            )

        # store answer to previous question
        else:
            context.chat_data.update({setting: update.message.text})

            self._get_chat_logger(chat.id).debug(
                f"Setting: \"{setting}\" = \"{context.chat_data.get(setting)}\""
            )

        settings = list(self._report_settings.keys())

        # update conversation state
        if setting == None:
            setting = settings[0]
        elif settings.index(setting) + 1 < len(settings):
            setting = settings[settings.index(setting)+1]

        # conversation is over: time for words is over!
        else:
            self._get_chat_logger(chat.id).info(
                f"Report settings: {context.chat_data}"
            )
            self._send_message(
                chat.id, path=self._data["msg"].joinpath("setting_end.md"),
                reply_markup=ReplyKeyboardRemove()
            )

            return ConversationHandler.END

        # ask question
        self._send_message(
            chat.id, path=self._data["msg"].joinpath(f"{setting}_setting.md"),
            reply_markup=ReplyKeyboardMarkup(
                np.array(self._report_settings[setting]).reshape(-1,1),
                one_time_keyboard=True
            )
        )

        return setting


    def _cancel_set_reports(
        self, update: Update, context: CallbackContext,
        invalid_setting: bool = False
    ) -> int:
        """/annulla command.
        Cancel current report setting conversation.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug("Cancelling setting")

        if invalid_setting:
            self._get_chat_logger(chat.id).debug(
                f"Invalid setting: \"{update.message.text}\""
            )

        # restore previous configuration
        previous = context.chat_data["previous_settings"].copy()
        context.chat_data.clear()
        context.chat_data.update(previous)

        self._get_chat_logger(chat.id).debug(
            f"Settings restored: {context.chat_data}"
        )

        self._send_message(
            chat.id, path=self._data["msg"].joinpath("cancel_setting.md"),
            reply_markup=ReplyKeyboardRemove()
        )

        if invalid_setting:
            self._send_message(
                chat.id, path=self._data["msg"].joinpath("invalid_setting.txt"),
                fmt=(update.message.text,), reply_markup=ReplyKeyboardRemove()
            )

        return ConversationHandler.END


    def _disable_reports(self, update: Update, context: CallbackContext) -> int:
        """/disattiva_report command.
        Unsubscribe user from receiveing reports.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug("/disattiva_report command")

        context.chat_data.clear()

        self._get_chat_logger(chat.id).info("Reports disabled")

        self._send_message(
            chat.id, path=self._data["msg"].joinpath("disable_reports.md")
        )


    def _report_status(self, update: Update, context:CallbackContext) -> None:
        """/stato_report command.
        Show report settings.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug("/stato_report command")

        settings = context.chat_data

        self._get_chat_logger(chat.id).debug(f"Settings: {settings}")

        if settings == {}:
            self._send_message(
                chat.id,
                path=self._data["msg"].joinpath("disabled_report_status.md")
            )
            return

        self._send_message(
            chat.id, path=self._data["msg"].joinpath("active_report_status.md"),
            fmt=(
                settings.get(key)
                for key in [
                    "frequency", "contagions_national", "contagions_regional",
                    "vaccines_national", "vaccines_regional"
                ]
            )
        )


    def _report_bug(self, update: Update, context: CallbackContext) -> None:
        """/bug command.
        Send \"report bug\" informative message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug("/bug command")

        self._send_message(
            chat.id, path=self._data["msg"].joinpath("report_bug.md")
        )


    def _feedback(self, update: Update, context: CallbackContext) -> None:
        """/feedback command.
        Send \"feedback\" informative message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self._get_chat_logger(chat.id).debug("/feedback command")

        self._send_message(
            chat.id, path=self._data["msg"].joinpath("feedback.md")
        )


    def _easter_eggs(self, update: Update, context: CallbackContext) -> None:
        """This is just for fun."""

        user = update.effective_user
        chat = update.effective_chat

        try:
            msg = update.message.text
        except:
            msg = update.edited_message.text

        if msg == "Chi è il tuo padrone?":
            self._send_message(
                chat.id, parse_mode="MarkdownV2",
                text="[Andrea Serpolla](https://github.com/cavfiumella) è il "
                     "mio padrone\."
            )


    def _update_regions_answers(self) -> None:
        """Update available regions in report settings."""

        self._logger.debug("Updating available regions")

        for key, area_column, df_key in zip(
            ["contagions", "vaccines"], ["denominazione_regione", "nome_area"],
            ["regional", "doses"]
        ):
            regions = self._db[key].get_df(df_key)
            regions = regions.loc[:, area_column].drop_duplicates()
            regions = regions.sort_values().tolist()

            self._report_settings[f"{key}_regional"] = ["Nessun report"]
            self._report_settings[f"{key}_regional"] += regions

            self._logger.debug(
                f"Available {key} regions: "
                f"{self._report_settings[f'{key}_regional']}"
            )


    def _format_report(self, report: Report, /, subtitle: str) -> str:
        """Format report generated by databases objects.

        Parameters:
        - report
        - subtitle: reports have title in the form \"Report <current-period>\";
                    subtitle is inserted generating \"Report <subtitle>
                    <current-period>\"

        Returns:
        formatted text
        """

        self._logger.debug("Formatting report")

        report = report.dropna()

        s = f"Report {subtitle} {report.name}\n"
        s += "-" * 40 + "\n"

        for key in report.index.tolist():
            s += key
            s += "\n"

            if "pct" in key.lower():
                s += "{:.1%}".format(report.loc[key])
            elif int(report.loc[key]) == report.loc[key]:
                s += "{:d}".format(int(report.loc[key]))
            else:
                s += "{:.1f}".format(report.loc[key])

            s += "\n"

        return s


    def _get_db_reports(
        self, chat_id: str, db_key: str, db_key_translation: str,
        files_keys: dict[str,str], current: str, fmt: str = "%Y-%m-%d"
    ) -> dict[str,Report]:
        """Based on user settings return subscribed reports for a certain
        database.

        Parameters:
        - chat_id: used to get chat report settings
        - db_key: database key, used to retrieve correct settings
        - db_key_translation: used in report key generated
        - files_keys: dict containing (area type, df file key) pairs where
                      area type can be \"national\" or \"regional\" and file
                      key is the key passed to Database.get_report method
        - current, fmt: documented in BaseDatabase.get_report

        Returns:
        dict of reports
        """

        settings = self._updater.dispatcher.chat_data[chat_id]

        self._get_chat_logger(chat_id).debug(
            f"Getting db reports: db_key = \"{db_key}\", "
            f"files_keys = {files_keys}, current = \"{current}\", "
            f"fmt = \"{fmt}\", settings = {settings}"
        )

        # (subtitle, report) pairs
        reports = {}

        if settings.get(f"{db_key}_national") == "Sì":
            reports[" ".join([db_key_translation, "Italia"])] \
            = self._db[db_key].get_report(
                files_keys["national"], current=current, fmt=fmt
            )

        region = settings.get(f"{db_key}_regional")

        if region not in [None, "Nessun report"]:
            reports[" ".join([db_key_translation, region])] \
            = self._db[db_key].get_report(
                files_keys["regional"], area=region, current=current,
                fmt=fmt
            )

        return reports


    def _send_reports(
        self, chat_id: int, /, current: str, fmt: str = "%Y-%m-%d"
    ) -> None:
        """Send reports to chat.

        Parameters:
        - chat_id
        - current, fmt: documented in BaseDatabase.get_report
        """

        self._get_chat_logger(chat_id).debug(
            f"Sending reports: current = \"{current}\", fmt = \"{fmt}\""
        )

        # generate reports
        reports = {}

        for key, key_translation, files_keys in zip(
            ["contagions", "vaccines"], ["contagi", "vaccini"],
            [
                {"national": "national", "regional": "regional"},
                {"national": "doses", "regional": "doses"},
            ]
        ):
            reports.update(self._get_db_reports(
                chat_id=chat_id, db_key=key, db_key_translation=key_translation,
                files_keys=files_keys, current=current, fmt=fmt
            ))

        # send reports

        text = ""

        for subtitle, report in reports.items():
            text += "\n" + self._format_report(report, subtitle=subtitle)

        self._send_message(chat_id, text=text)

        self._get_chat_logger(chat_id).info(f"Reports \"{current}\" delivered")


    def _report_scheduler_target(
        self, sleep: int, tz: str = "Europe/Rome", master_sleep: int = 10
    ) -> None:
        """Keep trying to send new reports.

        Parameters:
        - sleep: sleeping time in seconds between consecutive reports
                 sending attempts
        - tz: timestamps timezone
        - master_sleep: sleeping time in seconds between successive
                        iterations of target execution
        """

        self._logger.debug(
            f"Report scheduler target: self = {self}, sleep = {sleep}, "
            f"tz = \"{tz}\", master_sleep = {master_sleep}"
        )

        # previous reports sending attempt
        previous: pd.Timestamp = None

        while True:

            # bot object wants to stop the thread
            if self._stop_report_scheduler:
                self._logger.info("Stopping report scheduler")
                return

            # this is not the first iteration => master sleep
            if previous != None:
                time.sleep(master_sleep)

            now = pd.Timestamp.utcnow().tz_convert(tz)

            if previous != None and (now - previous).seconds <= sleep:
                continue # sleep

            self._logger.debug("Running report scheduler target")

            previous = now

            # do not disturb
            if now > pd.Timestamp(self._report_do_not_disturb[0], tz=tz) \
            or now < pd.Timestamp(self._report_do_not_disturb[1], tz=tz):
                self._logger.debug(
                    f"Report scheduler respects \"do not disturb\""
                )
                continue

            # update databases
            for db in self._db.values():
                db.update()

            for chat_id, settings in self._updater.dispatcher.chat_data.items():

                for frequency in self._report_settings["frequency"]:
                    fmt = self._frequency_fmt[frequency]

                    self._get_chat_logger(chat_id).debug(
                        f"Settings: {settings}"
                    )

                    current = now \
                    + pd.Timedelta(days=self._frequency_offset[frequency])
                    current = current.strftime(fmt)

                    # skip user
                    if settings.get("frequency") != frequency:
                        self._get_chat_logger(chat_id).debug(
                            "Skipping report delivery with frequency "
                            f"\"{frequency}\": not subscribed"
                        )
                        continue

                    # current report already sent
                    if current == settings.get("last_report"):
                        self._get_chat_logger(chat_id).debug(
                            "Skipping report delivery with frequency "
                            f"\"{frequency}\": already sent"
                        )
                        continue

                    try:
                        # send new report
                        self._send_reports(
                            chat_id, current=current, fmt=fmt
                        )

                        settings.update({"last_report": current})
                        self._updater.dispatcher.update_persistence()

                    except:
                        # unable to send report
                        self._get_chat_logger(chat_id).debug(
                            "Report delivery encountered an error: "
                            f"{traceback.format_exc()}"
                        )


    def _start_report_scheduler(
        self, sleep: int = 30*60, tz: str = "Europe/Rome"
    ) -> Thread:
        """Start report sender scheduler in a separate thread.

        Parameters:
        - sleep: sleeping time between scheduler iterations in seconds
        - tz: timestamps timezone

        Returns:
        - started thread
        """

        self._logger.debug(
            f"Starting report scheduler: sleep = {sleep}, tz = \"{tz}\""
        )

        thread = Thread(target=self._report_scheduler_target, args=(sleep, tz))
        self._logger.debug(f"Report scheduler created: {thread}")

        thread.start()
        self._logger.info("Report scheduler started")

        return thread


    def __init__(self, token: str, /, data: Optional[Dict[str,Path]] = None):
        """Build and start the bot.

        Parameters:
        - token: Telegram API token
        - data: dict containing paths to mybot data;
                data must contain the same keys given by MyBot._data
        """

        self._logger = getLogger(str(self))

        if data != None:
            if data.keys() != MyBot._data.keys():
                raise ValueError("invalid data parameter")
            self._data = data

        self._logger.debug(f"Data: {self._data}")

        self._db = {
            module: eval(module).Database()
            for module in ["contagions", "vaccines"]
        }

        self._logger.debug(f"Databases: {self._db}")

        self._update_regions_answers()

        # build bot

        self._updater = Updater(
            token=token,
            persistence=PicklePersistence(filename=self._data["pkl"])
        )

        # subscribe to reports handler
        self._updater.dispatcher.add_handler(ConversationHandler(
            entry_points=[CommandHandler("imposta_report", self._set_reports)],
            states = {
                setting: [
                    MessageHandler(
                        Filters.update.message \
                        & Filters.text(self._report_settings[setting]),
                        partial(self._set_reports, setting=setting)
                    ),
                    MessageHandler(
                        ~ Filters.update.edited_message,
                        partial(self._cancel_set_reports, invalid_setting=True)
                    )
                ]
                for setting in self._report_settings.keys()
            },
            fallbacks = [CommandHandler("annulla", self._cancel_set_reports)]
        ))

        for command, callback in {
            "start": self._start,
            "help": self._help,
            "disattiva_report": self._disable_reports,
            "stato_report": self._report_status,
            "bug": self._report_bug,
            "feedback": self._feedback
        }.items():
            self._updater.dispatcher.add_handler(CommandHandler(
                command, callback
            ))

        # easter eggs handler
        self._updater.dispatcher.add_handler(MessageHandler(
            Filters.text(["Chi è il tuo padrone?"]), self._easter_eggs
        ))

        self._updater.dispatcher.bot.set_my_commands(
            list(self._commands_descriptions.items())
        )

        # start bot
        self._updater.start_polling()
        self._logger.info(f"Bot started (token: \"{token}\")")

        # start report scheduler
        self._report_scheduler = self._start_report_scheduler()


    def __del__(self):
        """Stop bot and report scheduler."""

        if self._report_scheduler == None:
            self._logger.debug("No running report scheduler to stop")

        # stop report scheduler
        else:
            self._stop_report_scheduler = True
            timeout = 120

            self._logger.debug(f"Waiting {timeout} seconds thread termination")

            self._report_scheduler.join(timeout=timeout)

            if self._report_scheduler.is_alive():
                self._logger.warning("Thread is still running")

        # stop bot
        try:
            self._updater.stop()
            self._logger.info("Bot stopped")
        except:
            self._logger.warning(
                "Unable to safely stop bot on object deletion"
            )
