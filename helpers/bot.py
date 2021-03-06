
"""Telegram BOT sending Covid-19 updates."""


from _version import get_version
from .database import BaseDatabase, Contagions, Vaccines

from logging import getLogger, Logger
from typing import Dict, List, Tuple, Any, Optional, Union
from pathlib import Path
from threading import Thread
import json
import time
import traceback
import pandas as pd
import numpy as np
from telegram import (
    Update,
    Bot,
    Chat
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
from functools import partial
from collections import defaultdict


__version__ = get_version()
LOGGER = getLogger(__name__)


class Scheduler:
    """Scheduler class is a wrapper for threading.Thread class.
    It adds the functionality to start and stop a target function multiple times
    creating and deleting a Thread when necessary.

    This class should not be used as it is but as a base class for a derived
    class made for the purpose defining a method that acts as a target for the
    Scheduler and uses _stop_target to stop itself."""

    _logger: Logger = None

    _thread: Thread = None

    _target = None
    _args: Tuple = None
    _kwargs: Dict = None

    _stop_target: bool = False


    def __init__(self, target, args: Tuple = None, kwargs: Dict = None):
        """Parameters:
        - target: callable to use as Thread target and that stops when
                  Scheduler._stop_target is True
        - args: positional arguments to be passed to target
        - kwargs: keyword arguments to be passed to target
        """

        self._logger = getLogger(str(self))

        if args == None:
            args = tuple()

        if kwargs == None:
            kwargs =  {}

        self._target = target
        self._args = args
        self._kwargs = kwargs

        self._logger.debug(
            f"Scheduler created: args = {self._args}, kwargs = {self._kwargs}"
        )


    def start(self) -> None:
        """Start a new thread with target function."""

        self._thread = Thread(
            target = self._target, args = self._args,
            kwargs = self._kwargs
        )

        self._stop_target = False
        self._thread.start()

        self._logger.debug("Scheduler started")
        self._logger.debug(f"Scheduler thread: {self._thread}")


    def is_alive(self) -> bool:
        """Returns True if thread is running."""

        if self._thread != None:
            alive = self._thread.is_alive()
        else:
            alive = False

        self._logger.debug(f"Scheduler thread is alive: {alive}")

        return alive


    def stop(self, timeout: int = 120, errors = "ignore") -> None:
        """Stop thread running thread.

        Parameters:
        - timeout: wait timeout seconds that thread stops, then kill it
        - errors: when thread is not alive and stop is called an exception is
                  raised when errors is \"strict\" or nothing happens when
                  errors is \"ignore\"
        """

        self._logger.debug("Stopping scheduler")

        if errors not in ["strict", "ignore"]:
            self._logger.warning(
                f"Invalid errors \"{errors}\", falling back to \"ignore\""
            )

            errors = "ignore"

        if not self.is_alive():
            if errors == "strict":
                raise ValueError("thread is not running")
            elif errors == "ignore":
                return

        self._stop_target = True

        self._logger.debug(f"Waiting {timeout} seconds")
        self._thread.join(timeout)

        if self.is_alive():
            self._logger.warning("Scheduler is still running: killing it")

        del self._thread
        self._thread = None


    def __del__(self):
        """Safely stop scheduler on deletion."""

        self._logger.debug("Deleting scheduler")

        self.stop()


class Reporter(Scheduler):

    _logger: Logger = None

    _bot = None # MyBot object
    _db: Dict[str, BaseDatabase] = None

    _tz: str = "Europe/Rome"
    _do_not_disturb: Tuple = ("21:00", "10:00")

    # report delivery periods
    _periods: list[str] = ["giorno", "settimana", "mese"]

    # correspondig datetime fmt for frquencies
    _period_fmt: Dict[str, str] = {
        "giorno": "%Y-%m-%d",
        "settimana": "anno %Y, settimana %W",
        "mese": "%Y-%m"
    }

    # offsets used to determine current period in report generation;
    # values are (period, days offset) pairs
    _period_offset: Dict[str, int] = {
        "giorno": pd.Timedelta(hours = -14),
        "settimana": pd.Timedelta(days = -9),
        "mese": pd.Timedelta(days = -32)
    }

    # variables to use in reports: (db_name, (var_name, var_type))
    # variable types according to Reporter.get_report
    _db_variables: Dict[str, Dict[str,str]] = {
        "contagions": {
            "data": "date",
            "nuovi_positivi": "actual",
            "totale_positivi": "actual",
            "ricoverati_con_sintomi": "actual",
            "terapia_intensiva": "actual",
            "isolamento_domiciliare": "actual",
            "dimessi_guariti": "cumulative",
            "deceduti": "cumulative",
            "tamponi": "cumulative",
            "tamponi_test_molecolare": "cumulative",
            "tamponi_test_antigenico_rapido": "cumulative"
        },
        "vaccines": {
            "data_somministrazione": "date",
            "prima_dose": "actual",
            "seconda_dose": "actual",
            "pregressa_infezione": "actual",
            "dose_addizionale_booster": "actual"
        }
    }

    # db names italian translations
    _db_translations: Dict[str,str] = {
        "contagions": "contagi",
        "vaccines": "vaccini"
    }

    # files keys to use in generating reports:
    # (db_name, (national or regional, file_key))
    # file_key as used by BaseDatabase.get_df
    _db_files_keys: Dict[str, Dict[str,str]] = {
        "contagions": {"national": "national", "regional": "regional"},
        "vaccines": {"national": "doses", "regional": "doses"},
    }


    def get_period_fmt(self, period: str) -> str:
        """Return datetime fmt for passed period."""

        return self._period_fmt[period]


    def get_report(
        self, df: pd.DataFrame, /, variables: Dict[str, str], current: str,
        fmt: str = "%Y-%m-%d", errors: str = "strict"
    ) -> pd.DataFrame:
        """Generate data values variations between consecutive periods based on
        current and fmt args for given variables in df.

        Parameters:
        - df: dataframe
        - variables: dataframe's variables to consider, i.e. a dict containing
                     (column name, value type) pairs where implemented value
                     types are \"cumulative\", \"actual\" and \"date\"; \"date\"
                     variables are used to aggregate data and only one is used
        - current: current period timestamp formatted as given by fmt
        - fmt: datetime format, it determines how to aggregate data, e.g.
               * \"%Y-%m-%d\" will generate a report considering previous and
                 current day as consecutive periods (i.e. a day report),
               * \"%Y-%m\" will consider previous and current month as
                 consecutive periods (i.e. a month report)
        - errors: set if trying to continue execution or raise an
                  exception when some condition is not respected;
                  implemented values are \"strict\" and \"ignore\"

        Returns:
        report
        """

        self._logger.debug(
            f"Generating report: "
            f"\ndf = \n{df}"
            f"\nvariables = {json.dumps(variables, indent=4)}"
            f"\ncurrent = \"{current}\", fmt = \"{fmt}\", errors = \"{errors}\""
        )

        # errors fallback
        if errors not in ["strict", "ignore"]:
            self._logger.warning(
                f"Invalid errors \"{errors}\"; falling back to \"ignore\""
            )
            errors = "ignore"

        # check if there are some missing variables
        isin_var = np.isin(
            element=list(variables.keys()), test_elements=df.columns.tolist()
        )

        if not isin_var.all():
            s = "missing variables found; ignoring them: "
            s += str(np.array(list(variables.keys()))[isin_var].tolist())

            if errors == "strict":
                raise ValueError(s)
            elif errors == "ignore":
                self._logger.warning(s.capitalize())

        # check if there is one or more date variables
        is_date = np.apply_along_axis(
            lambda s: s == "date", arr=list(variables.values()), axis=0
        )

        if not is_date.any():
            raise ValueError("there is not a date variable in passed ones")

        date_columns = np.array(list(variables.keys()))[is_date].tolist()

        if is_date.sum() > 1:
            s = f"there are more than one date variable: {date_columns}"

            if errors == "strict":
                raise ValueError(s)
            elif errors == "ignore":
                s += f"; using \"{date_columns[0]}\" to aggregate data"
                self._logger.warning(s.capitalize())

        date_column = date_columns[0]
        date_column_fmt = "report_date"

        self._logger.debug(
            f"Date column: {date_column}; date column fmt: {date_column_fmt}"
        )

        # filter columns
        df = df.filter(variables.keys())

        # transform dates
        df.insert(
            loc=0, column=date_column_fmt,
            value=df.loc[:, date_column].apply(
                lambda t: pd.Timestamp(t).strftime(fmt)
            )
        )

        # check current date is present in dataframe
        if current not in df.loc[:, date_column_fmt].tolist():
            raise ValueError(
                f"dataframe does not contain current \"{current}\""
            )

        # get previous date
        dates_fmt = df.loc[:, date_column_fmt].drop_duplicates().sort_values()
        previous = dates_fmt.iloc[dates_fmt.tolist().index(current)-1]

        self._logger.debug(f"Previous: \"{previous}\"")

        # keep only current and previous dates to speed up calculations
        df = df.loc[df.loc[:, date_column_fmt].isin([previous, current])]

        # generate report
        report = pd.DataFrame(
            columns=["totale", "media", "dev std", "var pct"],
            dtype=object
        )

        for var, T in variables.items():
            sel = df.filter([date_column, date_column_fmt, var])

            if T == "actual":
                pass
            elif T == "cumulative": # convert in actual values
                sel = sel.drop(columns=date_column_fmt)
                sel = sel.groupby(date_column).max().diff()
                sel = sel.reset_index()
                sel.insert(
                    loc=0, column=date_column_fmt,
                    value=sel.loc[:, date_column].apply(
                        lambda t: pd.Timestamp(t).strftime(fmt)
                    )
                )
            else:
                continue

            sel = sel.drop(columns=date_column).groupby(date_column_fmt)
            values = list(map(
                lambda x: x.loc[current].values[0],
                [sel.sum(), sel.mean(), sel.std(), sel.mean().pct_change()*100]
            ))

            report = report.append(pd.DataFrame(
                [values], columns=report.columns, index=[var.replace("_", " ")]
            ))

        self._logger.debug(f"Returning report: \n{report}")

        return report


    def send_reports(
        self, chat_id: int, db_key: str, current: str, fmt: str = "%Y-%m-%d",
        settings: Optional[Dict[str,Any]] = None
    ) -> None:
        """Send reports to chat.

        Parameters:
        - chat_id
        - db_key: select database for reports
        - current, fmt: documented in Reporter.get_report
        - settings: report generation settings; if None they are read from
                    chat_data
        """

        self._bot.get_chat_logger(chat_id).debug(
            f"Sending reports: db_key = \"{db_key}\", current = \"{current}\", "
            f"fmt = \"{fmt}\", settings = {json.dumps(settings, indent=4)}"
        )

        if settings == None:
            settings = self._bot.get_chat_data(chat_id)

        # generate reports
        reports = []

        if settings.get(db_key) != None and "Italia" in settings.get(db_key):
            df = self._db[db_key].get_df(
                self._db_files_keys[db_key]["national"]
            )

            # aggregate data of the same date and area
            if db_key == "vaccines":
                df = df.groupby("data_somministrazione").sum().reset_index()

            report = self.get_report(
                df, variables = self._db_variables[db_key], current = current,
                fmt = fmt
            )

            report.name = \
            f"{self._db_translations[db_key].capitalize()} Italia"

            reports += [report]

        regions = settings.get(db_key)

        if type(regions) == str:
            regions = [regions]

        if regions != None:
            for region in regions:

                if region == "Italia":
                    continue

                df = self._db[db_key].get_df(
                    self._db_files_keys[db_key]["regional"],
                    area = region
                )

                # aggregate data of the same date and area
                if db_key == "vaccines":
                    df = df.groupby("data_somministrazione").sum().reset_index()

                report = self.get_report(
                    df, variables = self._db_variables[db_key],
                    current = current, fmt = fmt
                )

                report.name = \
                f"{self._db_translations[db_key].capitalize()} {region}"

                reports += [report]

        # format and send reports

        # textual format
        if settings.get("format") == "testuale":

            self._bot.get_chat_logger(chat_id).debug("Sending textual report")

            texts = []

            for report in reports:
                text = f"{report.name} ({current})\n"
                text += "-" * 40 + "\n"

                for row in report.index.tolist():
                    for col in report.columns.tolist():
                        text += col.capitalize() + " " + row
                        text += "\n"

                        x = report.loc[row,col]

                        if int(x) == x:
                            text += "{:d}".format(int(x))
                        else:
                            text += "{:.1f}".format(x)

                        text += "\n"

                texts += [text]

            # send messages
            for text in texts:
                self._bot.send_message(
                    chat_id, text=text,

                    # notify only the first msg
                    disable_notification = text != texts[0]
                )

        # excel format
        # this handles also missing format setting
        # (should not be but if there in case of a bug this is more secure)
        else:
            self._bot.get_chat_logger(chat_id).debug("Sending Excel report")

            path = f"/tmp/{db_key}.xlsx"

            with pd.ExcelWriter(path=path) as writer:
                for report in reports:
                    report.to_excel(writer, sheet_name=report.name)

            # send
            with open(path, "rb") as file:
                self._bot.send_document(
                    chat_id = chat_id, document = file.read(),
                    filename = f"{self._db_translations[db_key]}.xlsx",
                    caption = current.capitalize()
                )

        self._bot.get_chat_logger(chat_id).info(
            f"Reports \"{self._db_translations[db_key]} {current}\" delivered"
        )


    def _target(self, sleep: int = 30*60, master_sleep: int = 10) -> None:
        """Keep trying to send new reports.

        Parameters:
        - sleep: sleeping time in seconds between consecutive reports
                 sending attempts
        - master_sleep: sleeping time in seconds between successive
                        iterations of target execution
        """

        self._logger.debug(
            f"Target: sleep = {sleep}, master_sleep = {master_sleep}"
        )

        # previous reports sending attempt
        previous: pd.Timestamp = None

        while not self._stop_target:

            # this is not the first iteration => master sleep
            if previous != None:
                time.sleep(master_sleep)

            now = pd.Timestamp.utcnow().tz_convert(self._tz)

            if previous != None and (now - previous).seconds <= sleep:
                continue # sleep

            self._logger.debug("Running target")

            previous = now

            # do not disturb
            T0, T = tuple(map(
                lambda t: pd.Timestamp(t, tz=self._tz), self._do_not_disturb
            ))

            if T0 < T and T0 < now and now < T \
            or T0 > T and (T0 < now or now < T):
                self._logger.debug("Target respects \"do not disturb\"")
                continue

            # update databases
            for db in self._db.values():
                db.update()

            for chat_id, settings in self._bot.get_chat_data().items():
                for period in self._periods:

                    fmt = self._period_fmt[period]

                    self._bot.get_chat_logger(chat_id).debug(
                        f"Settings: {settings}"
                    )

                    current = now + self._period_offset[period]
                    current = current.strftime(fmt)

                    # skip user
                    if settings.get("period") != period:
                        self._bot.get_chat_logger(chat_id).debug(
                            "Skipping report delivery with period "
                            f"\"{period}\": not subscribed"
                        )
                        continue

                    for db_key in self._db.keys():

                        # current report already sent
                        if type(settings.get("last_report")) == dict \
                        and current == settings["last_report"].get(db_key):
                            self._bot.get_chat_logger(chat_id).debug(
                                "Skipping report delivery with period "
                                f"\"{period}\": already sent"
                            )
                            continue

                        try:
                            # send new report
                            self.send_reports(
                                chat_id, db_key, current=current, fmt=fmt
                            )

                            self._bot.update_last_report(
                                chat_id, db_key, current
                            )

                        except:
                            # unable to send report
                            self._bot.get_chat_logger(chat_id).debug(
                                "Report delivery encountered an error: "
                                f"{traceback.format_exc()}"
                            )


    def __init__(
        self, bot, db: Optional[Dict[str, BaseDatabase]] = None,
        tz: Optional[str] = None, do_not_disturb: Optional[Tuple[str]] = None
    ):
        """Parameters:
        - bot: a bot.MyBot object to use to send reports
        - tz: local timezone to use; if None, \"Europe/Rome\" is used
        - do_not_disturb: do not disturb times (start, end); if None,
                          (\"21:00\", \"10:00\") is used
        """

        self._logger = getLogger(str(self))

        self._bot = bot

        for var in ["db", "tz", "do_not_disturb"]:
            if eval(var) != None:
                exec(f"self._{var} = {var}")

        if db == None:
            self._db = {
                key: eval(f"{key.capitalize}()")
                for key in ["contagions", "vaccines"]
            }

        self._logger.debug(
            f"Reporter created: bot = {self._bot}, db = {self._db}, "
            f"tz = \"{self._tz}\", do_not_disturb = \"{self._do_not_disturb}\""
        )

        Scheduler.__init__(self, target=self._target)


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
    _scheduler: Reporter = None

    # data files locations
    _msg_dir: Path = Path("share/msg")
    _announcements_dir: Path = Path("share/announcements")
    _pkl_path: Path = Path("share/bot.pkl")

    # available commands; (command, description) pairs
    _commands_descriptions: Dict[str, str] = {
        "start": "messaggio di benvenuto",
        "help": "comandi disponibili e uso",
        "help_dati": "aiuto sui valori dei report",
        "attiva_report": "attiva gli aggiornamenti",
        "disattiva_report": "disattiva gli aggiornamenti",
        "stato_report": "visualizza impostazioni",
        "richiedi_report": "richiedi report specifico",
        "dashboard": "visualizza grafici su contagi e vaccinazioni",
        "bug": "segnala un errore",
        "feedback": "lascia un suggerimento",
        "versione": "visualizza versione bot"
    }

    # reports delivery settings; values are (setting, available options) pairs
    _settings: Dict[str, List[str]] = {
        "format": ["testuale", "excel"], # report format
        "period": ["giorno", "settimana", "mese"], # reference time period
        "contagions": ["Italia"], # selected areas (Italy or regions)
        "vaccines": ["Italia"] # selected areas (Italy or regions)
        # regions are appended later
    }

    # mandatory settings
    _mandatory: Dict[str,bool] = {
        "format": True,
        "period": True,
        "contagions": False,
        "vaccines": False
    }

    # settings with multiple answers allowed
    _multiples: Dict[str,bool] = {
        "format": False,
        "period": False,
        "contagions": True,
        "vaccines": True
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

            except:
                self.get_chat_logger(chat_id).debug(
                    "Unhandled exception while sending message: "
                    f"{traceback.format_exc()}"
                )
                return

        self.get_chat_logger(chat_id).debug(
            f"Sent message: parse_mode = \"{parse_mode}\", text = \"{text}\""
        )


    def send_document(self, chat_id: Union[int,str], *args, **kwargs) -> None:
        """Wrapper method for telegram.Bot.send_document."""

        self.get_chat_logger(chat_id).debug("Sending a document")

        while True:
            try:
                self._dispatcher.bot.send_document(chat_id, *args, **kwargs)
                break

            except ChatMigrated as ex:
                self.get_chat_logger(chat_id).debug("ChatMigration error")

                self._migrate_chat_data(chat_id, ex.new_chat_id)

                self.get_chat_logger(chat_id).info(
                    f"Chat migration: {chat_id} --> {ex.new_chat_id}"
                )

                chat_id = ex.new_chat_id

            except:
                self.get_chat_logger(chat_id).debug(
                    "Unhandled exception while sending document: "
                    f"{traceback.format_exc()}"
                )
                return


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


    def _help_data(self, update: Update, context: CallbackContext) -> None:
        """/help_dati command.
        Send help message for data variables.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("/help_dati command")

        self.send_message(chat.id, path=self._msg_dir.joinpath("help_data.md"))


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

        # conversation starts
        if setting == None:

            # remove old configuration
            try:
                context.chat_data.pop("previous_settings")
            except KeyError:
                pass

            # save current settings to restore later if needed
            previous = context.chat_data.copy()
            context.chat_data.clear()
            context.chat_data.update({"previous_settings": previous})

            self.get_chat_logger(chat.id).debug(
                "Previous settings: "
                f"{context.chat_data.get('previous_settings')}"
            )

            # update available regions
            self._update_regions()

        # store answer to previous question
        else:

            # parse answer
            text = update.message.text.lower()
            answer = []

            for option in self._settings[setting]:
                if option.lower() in text:
                    answer += [option]

            # invalid answer
            if self._mandatory[setting] and len(answer) == 0:
                return self._cancel_conversation(
                    update=update, context=context, invalid_answer=True
                )

            # if multiple answers are not allowed take just the first valid
            if not self._multiples[setting]:
                answer = answer[0]

            context.chat_data.update({setting: answer})

            self.get_chat_logger(chat.id).debug(
                f"Setting: \"{setting}\" = \"{context.chat_data.get(setting)}\""
            )

        settings = list(self._settings.keys())

        # ask first question
        if setting == None:
            setting = settings[0]

        # ask next question
        elif settings.index(setting) + 1 < len(settings):
            setting = settings[settings.index(setting)+1]

        # conversation is over: time for words is over!
        else:
            self.get_chat_logger(chat.id).info(
                f"Report settings: {context.chat_data}"
            )
            self.send_message(
                chat.id, path=self._msg_dir.joinpath("setting_end.md"),
            )

            # show current settings
            self._report_status(update, context)

            return ConversationHandler.END

        # ask question
        self.send_message(
            chat.id, path=self._msg_dir.joinpath(f"{setting}_setting.md"),
        )

        return setting


    def _request_report(
        self, update: Update, context: CallbackContext,
        setting: Optional[str] = None
    ) -> None:
        """/richiedi_report command.
        Request a specific report. Conversation used to get report settings
        is similar to the one used by `/attiva_report`.
        """

        chat_id = update.effective_chat.id

        self.get_chat_logger(chat_id).debug(
            f"/richiedi_report command, setting = \"{setting}\""
        )

        # read report settings using enable_reports
        if setting != "current":
            state = self._enable_reports(update, context, setting)

            # continue _enable_reports' conversation
            if state != ConversationHandler.END:
                return state

            # ask current period
            else:
                self.send_message(
                    chat_id, path=self._msg_dir.joinpath("current_request.md")
                )
                return "current"

        # store current date answer
        current = update.message.text

        self.get_chat_logger(chat_id).debug(
            f"User answered \"{current}\" to current date for report "
            "request"
        )

        # try send report
        try:
            # parse date
            current = pd.to_datetime(current, format="%Y-%m-%d")

            # format date
            # this must be corrected avoiding the use of schedulers private var
            fmt = self._scheduler.get_period_fmt(context.chat_data["period"])
            current = current.strftime(fmt)

            # send report
            for key in self._db.keys():
                self._scheduler.send_reports(chat_id, key, current, fmt)

        # unable to send requested report
        except:
            self.get_chat_logger(chat_id).debug(
                f"Unable to send requested report: {traceback.format_exc()}"
            )

            self.send_message(
                chat_id,
                path=self._msg_dir.joinpath("report_request_fail.md")
            )

        # restore settings
        if "previous_settings" in context.chat_data:
            previous = context.chat_data["previous_settings"].copy()
            context.chat_data.clear()
            context.chat_data.update(previous)
            self.get_chat_logger(chat_id).debug(
                f"Settings restored: {json.dumps(context.chat_data, indent=4)}"
            )

        else:
            context.chat_data.clear()
            self.get_chat_logger(chat_id).debug("No settings to restore")

        return ConversationHandler.END


    def _show_options(
        self, update: Update, context: CallbackContext, setting: str
    ) -> str:
        """/opzioni command.
        Show available options while in conversation with `/attiva_report`.
        """

        chat_id = update.effective_chat.id

        self.get_chat_logger(chat_id).debug("/opzioni command")

        self.send_message(
            chat_id, path=self._msg_dir.joinpath("options.md"),
            fmt = ("\- *" + "*\n\- *".join(self._settings[setting]) + "*",)
        )

        return setting


    def _cancel_conversation(
        self, update: Update, context: CallbackContext,
        invalid_answer: bool = False
    ) -> int:
        """/annulla command.
        Cancel current report setting conversation.
        """

        user = update.effective_user
        chat = update.effective_chat

        self.get_chat_logger(chat.id).debug("Cancelling setting")

        if invalid_answer:
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
            chat.id, path=self._msg_dir.joinpath("cancel_setting.md")
        )

        if invalid_answer:
            self.send_message(
                chat.id, path=self._msg_dir.joinpath("invalid_answer.md"),
                fmt=(update.message.text,)
            )

        # show current settings
        self._report_status(update, context)

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
            for key in ["format", "period", "contagions", "vaccines"]
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

        if msg == "Chi ?? il tuo padrone?":
            self.send_message(
                chat.id, parse_mode="MarkdownV2",
                text="[Andrea Serpolla](https://github.com/cavfiumella) ?? il "
                     "mio padrone\."
            )


    def _update_regions(self) -> None:
        """Update available regions in report settings."""

        self._logger.debug("Updating available regions")

        for key, area_column, df_key in zip(
            ["contagions", "vaccines"], ["denominazione_regione", "nome_area"],
            ["regional", "doses"]
        ):
            regions = self._db[key].get_df(df_key)
            regions = regions.loc[:, area_column].drop_duplicates()
            regions = regions.sort_values().tolist()

            self._settings[key] = ["Italia"] + regions

            self._logger.debug(
                f"Available {key} regions: {self._settings[key]}"
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
        """Start bot updater and scheduler."""

        self._updater.start_polling()
        self._scheduler.start()

        self._logger.info("Bot started")


    def idle(self):
        """Do not return until updater is running; exit safely when updater
        stops.
        """

        self._updater.idle()
        self.stop()


    def stop(self):
        """Stop bot updater."""

        if self._updater.running:
            self._updater.stop()
        else:
            self._logger.debug("No updater to stop")

        if self._scheduler.is_alive():
            self._scheduler.stop()
        else:
            self._logger.debug("No scheduler to stop")

        self._logger.info("Bot stopped")


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
        pkl_path: Optional[Path] = None, persistence: bool = True,
        tz: Optional[str] = None, do_not_disturb: Optional[Tuple] = None
    ):
        """Build and start the bot.

        Parameters:
        - token: Telegram API token
        - db: databases objects
        - msg_dir: dir to messages files
        - announcements_dir: dir to new versions announcement *.md files
        - pkl_path: path to persistence file
        - persistence: make bot persistent
        - tz, do_not_disturb: documented in `bot.Reporter.__init__`
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

        # bot

        self._logger.debug(f"Using token \"{token}\"")

        self._updater = Updater(
            token = token,
            persistence = PicklePersistence(filename=self._pkl_path) \
                          if persistence else None
        )
        self._dispatcher = self._updater.dispatcher

        # subscribe to reports handler

        # needed to give ConversationHandler's filters available regions to
        # filter
        self._update_regions()

        self._dispatcher.add_handler(ConversationHandler(
            entry_points=[CommandHandler("attiva_report", self._enable_reports)],
            states = {
                setting: [
                    CommandHandler("annulla", self._cancel_conversation),
                    CommandHandler(
                        "opzioni", partial(self._show_options, setting=setting)
                    ),
                    MessageHandler(
                        Filters.update.message & Filters.text,
                        partial(self._enable_reports, setting=setting)
                    )
                ]
                for setting in self._settings.keys()
            },
            fallbacks = [
                #CommandHandler("annulla", self._cancel_conversation),
                MessageHandler(
                    ~ Filters.update.edited_message,
                    partial(self._cancel_conversation, invalid_answer=True)
                )
            ]
        ))

        # request report conversation; this is similar to the previous one
        # for reports deliveries subscription

        states = {
            setting: [
                CommandHandler("annulla", self._cancel_conversation),
                CommandHandler(
                    "opzioni", partial(self._show_options, setting=setting)
                ),
                MessageHandler(
                    Filters.update.message & Filters.text,
                    partial(self._request_report, setting=setting)
                )
            ]
            for setting in self._settings.keys()
        }

        states["current"] = [
            CommandHandler("annulla", self._cancel_conversation),
            MessageHandler(
                Filters.update.message & Filters.text,
                partial(self._request_report, setting="current")
            )
        ]

        self._dispatcher.add_handler(ConversationHandler(
            entry_points=[
                CommandHandler("richiedi_report", self._request_report)
            ],
            states = states,
            fallbacks = [
                #CommandHandler("annulla", self._cancel_conversation),
                MessageHandler(
                    ~ Filters.update.edited_message,
                    partial(self._cancel_conversation, invalid_answer=True)
                )
            ]
        ))

         # chat migration handler

        self._dispatcher.add_handler(MessageHandler(
            Filters.status_update.migrate, self._chat_migration
        ))

        # other handlers
        for command, callback in {
            "start": self._start,
            "help": self._help,
            "help_dati": self._help_data,
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
            Filters.text(["Chi ?? il tuo padrone?"]), self._easter_eggs
        ))

        self._dispatcher.bot.set_my_commands(
            list(self._commands_descriptions.items())
        )

        # version announcement

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

        # report scheduler

        self._scheduler = Reporter(self, self._db, tz, do_not_disturb)


    def __del__(self):
        """Stop the bot on deletion"""

        self._logger.debug("Deleting bot")

        try:
            self.stop()
        except:
            self._logger.error("Unable to stop safely")
            self._logger.error(traceback.format_exc())
