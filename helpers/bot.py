
"""Telegram BOT sending Covid-19 updates."""


from _version import get_version
from .database import BaseDatabase, Contagions, Vaccines

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
    Dispatcher,
    CallbackContext,
    CommandHandler,
    PicklePersistence,
    ConversationHandler,
    MessageHandler
)
from telegram.error import ChatMigrated, BadRequest
from telegram.ext.filters import Filters
import pandas as pd
import numpy as np
from functools import partial
import traceback
from collections import defaultdict
import json


__version__ = get_version()
LOGGER = getLogger(__name__)


class MyBot:
    """This is my BOT.

    Logging:
      To discriminate operations done for different chats, logging for user
      actions is done using one Logger per chat.
    """

    # object logger
    _logger: Logger = None

    # databases
    _db: Dict[str, BaseDatabase] = None

    _updater: Updater = None
    _dispatcher: Dispatcher = None

    # data files locations
    _msg_dir: Path = Path("share/msg")
    _announcements_dir: Path = Path("share/announcements")
    _pkl_path: Path = Path("share/bot.pkl")

    # available commands; (command, description) pairs
    _commands_descriptions: Dict[str, str] = {
        "start": "messaggio di benvenuto",
        "help": "comandi disponibili e uso",
        "attiva_report": "attiva gli aggiornamenti",
        "disattiva_report": "disattiva gli aggiornamenti",
        "stato_report": "visualizza impostazioni",
        "dashboard": "visualizza grafici su contagi e vaccinazioni",
        "bug": "segnala un errore",
        "feedback": "lascia un suggerimento",
        "versione": "visualizza versione bot"
    }

    # reports settings; values are (setting, available answers) pairs
    _report_settings: Dict[str, List[str]] = {
        "format": ["Testuale", "Excel"],
        "frequency": ["Giornaliera", "Settimanale", "Mensile"],
        "contagions_national": ["Sì", "No"],
        "contagions_regional": None,
        "vaccines_national": ["Sì", "No"],
        "vaccines_regional": None
    }


    def get_chat_logger(self, chat_id: int, /) -> Logger:
        """Get Logger for chat."""

        return getLogger(f"{self}.chat_{chat_id}")


    def _migrate_chat_data():
        """Migrate chat data from old id to new id.

        Parameters:
        - old_id: old chat id
        - new_id: new chat id
        """

        self._logger.debug(f"Migrating chat data: {old_id} --> {new_id}")

        # transfer data
        self._dispatcher.chat_data[new_id].update(
            self._dispatcher.chat_data[old_id]
        )
        del self._dispatcher.chat_data[old_id]

        self._logger.debug(
            "Chat data migrated:"
            f"\nold: {json.dumps(self._dispatcher.chat_data[old_id], indent=4)}"
            f"\nnew: {json.dumps(self._dispatcher.chat_data[new_id], indent=4)}"
        )


    def send_message(
        self, chat_id: Union[int,str], /, parse_mode: str = "html",
        path: Optional[Path] = None, text: Optional[str] = None,
        disable_web_page_preview: bool = True, fmt: Optional[Tuple[Any]] = None,
        **kwargs
    ) -> None:
        """Send message.

        Parameters:
        - chat_id
        - parse_mode: telegram.Bot.send_message parse modes
        - path: file containing the message, if path is a file with extension
                \"*.md\" parse_mode is converted to \"MarkdownV2\"
        - text: text to send
        - disable_web_page_preview
        - fmt: call str.format on text message with this arguments
        - additional kwargs: passed to telegram.Bot.send_message

        One between path and text must be a valid argument, otherwise a
        ValueError is raised.
        """

        if path == None and text == None:
            raise ValueError("path and text are None")

        if path != None:
            with path.open() as file:
                text = file.read()

            if path.name.split(".")[-1] == "md":
                parse_mode = "MarkdownV2"

                self.get_chat_logger(chat_id).debug(
                    "Markdown file detected: parse_mode changed to "
                    f"\"{parse_mode}\""
                )

        if fmt != None:
            text = text.format(*fmt)

        while True:
            try:
                self._dispatcher.bot.send_message(
                    chat_id=chat_id, parse_mode=parse_mode, text=text,
                    disable_web_page_preview=True, **kwargs
                )
                break

            except ChatMigrated as ex:
                self.get_chat_logger(chat_id).debug("ChatMigration error")

                self._migrate_chat_data(chat_id, ex.new_chat_id)

                self.get_chat_logger(chat_id).info(
                    f"Chat migration: {chat_id} --> {ex.new_chat_id}"
                )

                chat_id = ex.new_chat_id

            except BadRequest as ex:

                if parse_mode != "MarkdownV2" \
                or "is reserved and must be escaped" not in ex.message:
                    raise

                char = ex.message[
                    ex.message.find("character") + len("character") + 2
                ]

                self._logger.debug(
                    f"Unescaped character \"{char}\" in \"{text}\""
                )

                text = text.replace(f"\{char}", char)
                text = text.replace(char, f"\{char}")

                self._logger.debug(f"Corrected text: \"{text}\"")

        self.get_chat_logger(chat_id).debug(
            f"Sent message: parse_mode = \"{parse_mode}\", text = \"{text}\""
        )


    def send_document(self, chat_id: Union[int,str], *args, **kwargs) -> None:
        """Wrapper method for telegram.Bot.send_document."""

        self.get_chat_logger(chat_id).debug("Sending a document")

        self._dispatcher.bot.send_document(chat_id, *args, **kwargs)


    def _start(self, update: Update, context: CallbackContext) -> None:
        """/start command.
        Send a welcome message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/start command")
        self.get_chat_logger(chat.id).info(f"New chat {chat.id}")

        if user.first_name != None and user.first_name != "":
            fmt = (user.first_name,)
        else:
            # fallback
            fmt = (user.username,)

        self.send_message(
            chat.id, path=self._msg_dir.joinpath("start.md"), fmt=fmt
        )


    def _help(self, update: Update, context: CallbackContext) -> None:
        """/help command.
        Send help message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/help command")

        self.send_message(chat.id, path=self._msg_dir.joinpath("help.md"))


    def _enable_reports(
        self, update: Update, context: CallbackContext,
        setting: Optional[str] = None
    ) -> Union[str,int]:
        """/attiva_report command.
        Conversate with user to set reports.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug(
            f"/attiva_report command, setting = \"{setting}\""
        )

        # conversation starts, store current configuration to restore it later
        # if needed
        if setting == None:
            context.chat_data.update({"previous_settings": None})
            previous = context.chat_data.copy()
            context.chat_data.clear()
            context.chat_data.update({"previous_settings": previous})

            self.get_chat_logger(chat.id).debug(
                "Previous settings: "
                f"{context.chat_data.get('previous_settings')}"
            )

        # store answer to previous question
        else:

            # not a regional setting
            if setting == None or "regional" not in setting:
                context.chat_data.update({setting: update.message.text})

            # regional setting
            else:

                # append to list or create a new one with regions
                if setting in context.chat_data:
                    # avoid inserting duplicates
                    if update.message.text not in context.chat_data[setting]:
                        context.chat_data[setting] += [update.message.text]
                else:
                    context.chat_data.update({setting: [update.message.text]})

            self.get_chat_logger(chat.id).debug(
                f"Setting: \"{setting}\" = \"{context.chat_data.get(setting)}\""
            )

        settings = list(self._report_settings.keys())

        # ask first question
        if setting == None:
            setting = settings[0]

        # keep asking for more regions
        elif "regional" in setting and update.message.text != "Nessun report":
            pass

        # go to the next question
        elif settings.index(setting) + 1 < len(settings):
            setting = settings[settings.index(setting)+1]

        # conversation is over: time for words is over!
        else:

            # remove unneeded "Nessun report" values in multiple regions lists
            for key in context.chat_data.keys():
                if "regional" in key and len(context.chat_data[key]) > 1:
                    context.chat_data[key].remove("Nessun report")

            self.get_chat_logger(chat.id).info(
                f"Report settings: {context.chat_data}"
            )
            self.send_message(
                chat.id, path=self._msg_dir.joinpath("setting_end.md"),
                reply_markup=ReplyKeyboardRemove()
            )

            return ConversationHandler.END

        # update available regions
        if "regional" in setting:
            self._update_regions_answers()

        # ask question
        self.send_message(
            chat.id, path=self._msg_dir.joinpath(f"{setting}_setting.md"),
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

        self.get_chat_logger(chat.id).debug("Cancelling setting")

        if invalid_setting:
            self.get_chat_logger(chat.id).debug(
                f"Invalid setting: \"{update.message.text}\""
            )

        # restore previous configuration
        previous = context.chat_data["previous_settings"].copy()
        context.chat_data.clear()
        context.chat_data.update(previous)

        self.get_chat_logger(chat.id).debug(
            f"Settings restored: {context.chat_data}"
        )

        self.send_message(
            chat.id, path=self._msg_dir.joinpath("cancel_setting.md"),
            reply_markup=ReplyKeyboardRemove()
        )

        if invalid_setting:
            self.send_message(
                chat.id, path=self._msg_dir.joinpath("invalid_setting.md"),
                fmt=(update.message.text,), reply_markup=ReplyKeyboardRemove()
            )

        return ConversationHandler.END


    def _disable_reports(self, update: Update, context: CallbackContext) -> int:
        """/disattiva_report command.
        Unsubscribe user from receiveing reports.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/disattiva_report command")

        context.chat_data.clear()

        self.get_chat_logger(chat.id).info("Reports disabled")

        self.send_message(
            chat.id, path=self._msg_dir.joinpath("disable_reports.md")
        )


    def _report_status(self, update: Update, context:CallbackContext) -> None:
        """/stato_report command.
        Show report settings.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/stato_report command")

        settings = context.chat_data

        self.get_chat_logger(chat.id).debug(f"Settings: {settings}")

        if settings == {}:
            self.send_message(
                chat.id,
                path=self._msg_dir.joinpath("disabled_report_status.md")
            )
            return

        # build send_message fmt argument
        fmt = [
            settings.get(key)
            for key in [
                "frequency", "contagions_national", "contagions_regional",
                "vaccines_national", "vaccines_regional"
            ]
        ]

        # convert list to a nice string for printing
        for i in range(len(fmt)):
            if type(fmt[i]) == list:
                fmt[i] = ", ".join(fmt[i]).rstrip(", ")

        self.send_message(
            chat.id, path=self._msg_dir.joinpath("report_status.md"),
            fmt=tuple(fmt)
        )


    def _dashboard(self, update: Update, context: CallbackContext) -> None:
        """/dashboard command.
        Send a link to an external dashboard of data.
        """

        chat_id = update.effective_chat.id

        self.get_chat_logger(chat_id).debug("/dashboard command")

        self.send_message(chat_id, path=self._msg_dir.joinpath("dashboard.md"))


    def _report_bug(self, update: Update, context: CallbackContext) -> None:
        """/bug command.
        Send \"report bug\" informative message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/bug command")

        self.send_message(
            chat.id, path=self._msg_dir.joinpath("report_bug.md")
        )


    def _feedback(self, update: Update, context: CallbackContext) -> None:
        """/feedback command.
        Send \"feedback\" informative message.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/feedback command")

        self.send_message(
            chat.id, path=self._msg_dir.joinpath("feedback.md")
        )


    def _version(self, update: Update, context: CallbackContext) -> None:
        """/versione command.
        Send bot version.
        """

        chat_id = update.effective_chat.id

        self.get_chat_logger(chat_id).debug("/versione command")

        self.send_message(
            chat_id, path=self._msg_dir.joinpath("version.md"),
            fmt=(__version__,)
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
            self.send_message(
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


    def _chat_migration(
        self, update: Update, context: CallbackContext
    ) -> None:
        """Handle chat migration updates. These updates are generally sent when
        a group becomes a supergroup.
        This method calls MyBot._migrate_chat_data to transfer chat_data to the
        new id.
        """

        self.get_chat_logger(old_id).debug("Chat migration update received")

        msg = update.message
        old_id = msg.migrate_from_chat_id or msg.chat_id
        new_id = msg.migrate_to_chat_id or msg.chat_id

        self._migrate_chat_data(old_id, new_id)

        self.get_chat_logger(old_id).info(
            f"Chat migration: {old_id} --> {new_id}"
        )


    def start(self):
        """Start bot updater."""

        self._updater.start_polling()
        self._logger.info("Bot updater started")


    def idle(self):
        """Do not return until updater is running."""

        self._updater.idle()
        self._logger.info("Bot updater stopped")


    def stop(self):
        """Stop bot updater."""

        if self._updater.running:
            self._updater.stop()
        else:
            self._logger.debug("No updater to stop")

        self._logger.info("Bot updater stopped")


    def get_chat_data(
        self, chat_id: Optional[str] = None, /
    ) -> Union[defaultdict, dict]:
        """Get a copy of stored chat data.

        Parameters:
        - chat_id: chat id of data to be returned; if None, all chat_data is
                   returned
        """

        data = self._dispatcher.chat_data.copy()

        if chat_id != None:
            data = data[chat_id]

        self._logger.debug(
            "Returning chat_data copy:" + \
            f"\nchat_id = {chat_id}: {json.dumps(data, indent=4)}"
            if chat_id != None else \
            f"\nchat_data: {json.dumps(data, indent=4)}"
        )

        return data


    def update_last_report(self, chat_id: int, db_key: str, t: str) -> None:
        """Update last_report timestamp for chat_id, db report with t."""

        self.get_chat_logger(chat_id).debug(f"Updating {db_key} last_report")

        if type(self._dispatcher.chat_data[chat_id].get("last_report")) == dict:
            self._dispatcher.chat_data[chat_id]["last_report"].update(
                {db_key: t}
            )
        else:
            self._dispatcher.chat_data[chat_id]["last_report"] = {db_key: t}

        self._dispatcher.update_persistence()

        self.get_chat_logger(chat_id).debug(
            "Last report: "
            f"{self._dispatcher.chat_data[chat_id]['last_report']}"
        )


    def __init__(
        self, token: str, db: Optional[Dict[str, BaseDatabase]] = None,
        msg_dir: Optional[Path] = None,
        announcements_dir: Optional[Path] = None,
        pkl_path: Optional[Path] = None,
        persistence: bool = True,
    ):
        """Build and start the bot.

        Parameters:
        - db: databases objects
        - token: Telegram API token
        - msg_dir: dir to messages files
        - announcements_dir: dir to new versions announcement *.md files
        - pkl_path: path to persistence file
        - persistence: make bot persistent
        """

        self._logger = getLogger(str(self))

        for var in ["msg_dir", "pkl_path", "db"]:
            if eval(var) != None:
                exec(f"self._{var} = {var}")

        # databases
        if db == None:
            self._db = {
                key: eval(f"{key.capitalize()}()")
                for key in ["contagions", "vaccines"]
            }

        self._logger.debug(
            f"Creating bot: msg_dir = \"{self._msg_dir}\", "
            f"pkl_path = \"{self._pkl_path}\", db = \"{self._db}\""
        )

        self._update_regions_answers()

        # bot

        self._logger.debug(f"Using token \"{token}\"")

        self._updater = Updater(
            token = token,
            persistence = PicklePersistence(filename=self._pkl_path) \
                          if persistence else None
        )
        self._dispatcher = self._updater.dispatcher

        # subscribe to reports handler
        self._dispatcher.add_handler(ConversationHandler(
            entry_points=[CommandHandler("attiva_report", self._enable_reports)],
            states = {
                setting: [MessageHandler(
                    Filters.update.message \
                    & Filters.text(self._report_settings[setting]),
                    partial(self._enable_reports, setting=setting)
                )]
                for setting in self._report_settings.keys()
            },
            fallbacks = [
                CommandHandler("annulla", self._cancel_set_reports),
                MessageHandler(
                    ~ Filters.update.edited_message,
                    partial(self._cancel_set_reports, invalid_setting=True)
                )
            ]
        ))

        self._dispatcher.add_handler(MessageHandler(
            Filters.status_update.migrate, self._chat_migration
        ))

        for command, callback in {
            "start": self._start,
            "help": self._help,
            "disattiva_report": self._disable_reports,
            "stato_report": self._report_status,
            "dashboard": self._dashboard,
            "bug": self._report_bug,
            "feedback": self._feedback,
            "versione": self._version
        }.items():
            self._dispatcher.add_handler(CommandHandler(command, callback))

        # easter eggs handler
        self._dispatcher.add_handler(MessageHandler(
            Filters.text(["Chi è il tuo padrone?"]), self._easter_eggs
        ))

        self._dispatcher.bot.set_my_commands(
            list(self._commands_descriptions.items())
        )

        # new version
        if "__version__" in self._dispatcher.bot_data \
        and __version__ != self._dispatcher.bot_data["__version__"]:

            self._logger.info(f"New version {__version__}")

            # save new version
            self._dispatcher.bot_data["__version__"] = __version__
            self._dispatcher.update_persistence()

            # announce new version
            path = self._announcements_dir.joinpath(f"{__version__}.md")

            if path.exists():
                for chat_id in self._dispatcher.chat_data.keys():
                    self.send_message(
                        chat_id, path=path, disable_notification=True,
                        fmt=(__version__.replace(".", "\."),)
                    )
                self._logger.info("New version announced")
            else:
                self._logger.debug(f"No announcement for version {__version__}")

        # save version if it is not
        if "__version__" not in self._dispatcher.bot_data:
            self._dispatcher.bot_data["__version__"] = __version__
            self._dispatcher.update_persistence()

        self._logger.debug(f"Bot data: {self._dispatcher.bot_data}")


    def __del__(self):
        """Stop the bot on deletion"""

        self._logger.debug("Deleting bot")

        try:
            self.stop()
        except:
            self._logger.error("Unable to stop safely")
            self._logger.error(traceback.format_exc())
