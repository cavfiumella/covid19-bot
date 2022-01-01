
from .database import BaseDatabase
from . import contagions, vaccines
from .bot import MyBot

from logging import getLogger, Logger
from typing import Dict, Tuple, Optional
import pandas as pd
import numpy as np
from threading import Thread
import json
import time
import traceback


LOGGER = getLogger(__name__)


# types aliases
Report = pd.Series


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

    _bot: MyBot = None
    _db: Dict[str, BaseDatabase] = None

    _tz: str = "Europe/Rome"
    _do_not_disturb: Tuple = ("21:00", "10:00")

    # report delivery frequencies
    _frequencies: list[str] = ["giornaliera", "settimanale", "mensile"]

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


    def get_report(
        self, df: pd.DataFrame, /, variables: Dict[str, str], current: str,
        fmt: str = "%Y-%m-%d", errors: str = "strict"
    ) -> Report:
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
        report = pd.Series(name=current, dtype=object)
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

            # insert in report
            for name, value in zip(
                ["totale", "media", "dev std", "var pct"],
                map(
                    lambda x: x.loc[current].values[0],
                    [sel.sum(), sel.mean(), sel.std(), sel.mean().pct_change()]
                )
            ):
                index = " ".join([name, var.replace("_", " ")]).capitalize()
                report[index] = value

        self._logger.debug(f"Returning report: \n{report}")

        return report


    def format_report(self, report: Report, /) -> str:
        """Format report generated by get_report.
        Values containing \"pct\" in their index are formatted as percentages.

        Parameters:
        - report

        Returns:
        textual report
        """

        self._logger.debug(f"Formatting report: \n{report}")

        self._logger.debug(f"Dropping {report.isnull().sum()} NaN")
        report = report.dropna()

        s = f"{report.name}\n"
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


    def send_reports(
        self, chat_id: int, /, current: str, fmt: str = "%Y-%m-%d"
    ) -> None:
        """Send reports to chat.

        Parameters:
        - chat_id
        - current, fmt: documented in Reporter.get_report
        """

        self._bot.get_chat_logger(chat_id).debug(
            f"Sending reports: current = \"{current}\", fmt = \"{fmt}\""
        )

        settings = self._bot.get_chat_data(chat_id)

        # generate reports
        reports = []

        for key in self._db.keys():

            if settings.get(f"{key}_national") == "Sì":
                report = self.get_report(
                    self._db[key].get_df(self._db_files_keys[key]["national"]),
                    variables = self._db_variables[key], current = current,
                    fmt = fmt
                )

                report.name = f"Report {self._db_translations[key]} Italia " \
                              f"{current}"

                reports += [report]

            region = settings.get(f"{key}_regional")

            if region not in [None, "Nessun report"]:
                report = self.get_report(
                    self._db[key].get_df(
                        self._db_files_keys[key]["regional"], area = region
                    ),
                    variables = self._db_variables[key],
                    current = current, fmt = fmt
                )

                report.name = f"Report {self._db_translations[key]} {region} " \
                              f"{current}"

                reports += [report]

        # send reports
        self._bot.send_message(
            chat_id, text="\n".join(list(map(self.format_report, reports)))
        )

        self._bot.get_chat_logger(chat_id).info(
            f"Reports \"{current}\" delivered"
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

                for frequency in self._frequencies:
                    fmt = self._frequency_fmt[frequency]

                    self._bot.get_chat_logger(chat_id).debug(
                        f"Settings: {settings}"
                    )

                    current = now \
                    + pd.Timedelta(days=self._frequency_offset[frequency])
                    current = current.strftime(fmt)

                    # skip user
                    if settings.get("frequency") != frequency:
                        self._bot.get_chat_logger(chat_id).debug(
                            "Skipping report delivery with frequency "
                            f"\"{frequency}\": not subscribed"
                        )
                        continue

                    # current report already sent
                    if current == settings.get("last_report"):
                        self._bot.get_chat_logger(chat_id).debug(
                            "Skipping report delivery with frequency "
                            f"\"{frequency}\": already sent"
                        )
                        continue

                    try:
                        # send new report
                        self.send_reports(
                            chat_id, current=current, fmt=fmt
                        )

                        self._bot.update_chat_data(
                            {"last_report": current}, chat_id
                        )

                    except:
                        # unable to send report
                        self._bot.get_chat_logger(chat_id).debug(
                            "Report delivery encountered an error: "
                            f"{traceback.format_exc()}"
                        )


    def __init__(
        self, bot: MyBot, tz: Optional[str] = None,
        do_not_disturb: Optional[Tuple[str]] = None
    ):
        """Parameters:
        - bot: a bot.MyBot object to use to send reports
        - tz: local timezone to use; if None, \"Europe/Rome\" is used
        - do_not_disturb: do not disturb times (start, end); if None,
                          (\"21:00\", \"10:00\") is used
        """

        self._logger = getLogger(str(self))

        self._bot = bot
        self._db = {}

        for key in ["contagions", "vaccines"]:
            self._db[key] = eval(f"{key}.Database()")

        for var in ["tz", "do_not_disturb"]:
            if eval(var) != None:
                exec(f"self._{var} = {var}")

        self._logger.debug(
            f"Reporter created: bot = {self._bot}, db = {self._db}, "
            f"tz = \"{self._tz}\", do_not_disturb = \"{self._do_not_disturb}\""
        )

        Scheduler.__init__(self, target=self._target)