
"""Data collection and time developing reports generations."""


from logging import getLogger, Logger
from typing import Dict, List, Tuple, Union, Optional
from pathlib import Path
import os
from urllib.request import urlopen
import numpy as np
import pandas as pd


LOGGER = getLogger(__name__)


# data resources aliases
Resource = Dict[str, Union[str, Path]]
RemoteResource = Dict[str, str]
LocalResource = Dict[str, Path]

# data time developing reports
Report = pd.Series


class BaseDatabase:
    """Base class for databases derived classes.

    Logging:
      To discriminate log messages coming from different derived classes
      objects, logging is performed using one Logger per object.
    """

    # object logger
    _logger: Logger = None

    _remote: RemoteResource = {
        "base_url": "https://raw.githubusercontent.com",
        "repo": None,
        "branch": "main",
        "files": None
    }

    _local: LocalResource = {
        "dir": Path("share"),
        "files": None
    }


    def _get_path(
        self, x: Resource, /, base_keys: List[str], file_key: str
    ) -> str:
        """Get path to a remote or local file.

        Parameters:
        - x: data resource
        - base_keys: ordered sequence of path base components specified by their
                     keys as resource's fields
        - file_key: key of a resource file that makes the last part of path

        Returns:
        string path
        """

        path = "/".join([str(x[key]) for key in base_keys])
        path += "/" + x["files"][file_key]

        self._logger.debug(f"Returning path \"{path}\"")

        return path


    def _get_remote_path(self, file_key: str, /) -> str:
        """Get path to a remote file.
        Parameters documented in _get_path method.
        """

        return self._get_path(
            self._remote, base_keys=["base_url", "repo", "branch"],
            file_key=file_key
        )


    def _get_local_path(self, file_key: str, /) -> Path:
        """Get path to a local file.
        Parameters documented in _get_path method.
        """

        return Path(
            self._get_path(self._local, base_keys=["dir"], file_key=file_key)
        )


    def update(self, *args) -> None:
        """Update local files with remote's.
        Data are downloaded without checking if remote files are effectively
        newer.

        Parameters:
        - additional args: keys of files to update.
        """

        self._logger.debug("Updating database")

        if not self._local["dir"].exists():
            os.mkdir(self._local["dir"])

            self._logger.info(f"New directory \"{self._local['dir']}\"")

        if len(args) == 0:
            keys = list(self._remote["files"].keys())
        else:
            keys = list(args)

        for key in keys:
            remote_path = self._get_remote_path(key)
            local_path = self._get_local_path(key)

            with open(local_path, "w") as file:
                s = urlopen(remote_path).read()
                if type(s) == bytes:
                    s = s.decode()
                file.write(s)

            self._logger.debug(f"Written file \"{local_path}\"")


    def __init__(self, /, remote: RemoteResource, local: LocalResource):
        """Parameters:
        - remote: remote resource containing required fields given by
                  BaseDatabase._remote
        - local: local resource containing required fields given by
                 BaseDatabase._local
        """

        self._logger = getLogger(str(self))

        # check keys
        for var in ["remote", "local"]:
            if not eval(f"BaseDatabase._{var}.keys() == {var}.keys()"):
                raise ValueError(f"invalid {var} parameter")

        # check if all remote files are present in local
        if not np.isin(
            element=list(remote["files"].keys()),
            test_elements=list(local["files"].keys())
        ).all():
            raise ValueError("local files do not contain all remote files")

        # warn if not all local files are present in remote
        if not np.isin(
            element=list(local["files"].keys()),
            test_elements=list(remote["files"].keys())
        ).all():
            self._logger.warning(
                "Remote files do not contain all local files;"
                "ignoring those files"
            )

        # store args
        for var in ["remote", "local"]:
            exec(f"self._{var} = {var}")

        self._logger.debug(
            f"Database created: self = {self}, remote = {self._remote}, "
            f"local = {self._local}"
        )

        self.update()


    def get_df(
        self, key: str, /, area: Optional[str] = None,
        area_column: Optional[str] = "nome_area", errors: str = "strict",
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """Get dataframe.

        Parameters:
        - key: csv file key (e.g. \"deliveries\")
        - area: area name, if None return data without filtering areas
        - area_column: column containing areas names
        - errors: if unable to get area, an exception is raised when errors is
                  \"strict\"; implemented values are \"strict\" and \"ignore\"
        - additional kwargs: passed to pandas.read_csv
        """

        # errors fallback
        if errors not in ["strict", "ignore"]:
            self._logger.warning(
                f"Invalid errors \"{errors}\"; falling back to \"ignore\""
            )
            errors = "ignore"

        self._logger.debug(f"Returning \"{key}\" dataframe")

        df = pd.read_csv(self._get_local_path(key), **kwargs)

        if area == None:
            return df

        # wants a region

        self._logger.debug(f"Selecting area \"{area}\" in \"{area_column}\"")

        if area_column not in df.columns.tolist():
            s = f"dataframe does not contain \"{area_column}\""

            if errors == "strict":
                raise ValueError(s)
            elif errors == "ignore":
                self._logger.warning(s.capitalize())
                return None

        if area not in df.loc[:, area_column].tolist():
            s = f"no data for region \"{area}\""

            if errors == "strict":
                raise ValueError(s)
            elif errors == "ignore":
                self._logger.warning(s.capitalize())
                return None

        df = df.loc[df.loc[:, area_column] == area].drop(columns=area_column)

        return df


    def get_report(
        self, key: str, /, variables: Dict[str, str], current: str,
        fmt: str = "%Y-%m-%d", area: Optional[str] = None,
        errors: str = "strict"
    ) -> Report:
        """Generate data values variations between consecutive periods based on
        current and fmt args.

        Parameters:
        - key: dataframe's csv file key
        - variables: dataframe's variables to consider, i.e. a dict containing
                     (column name, value type) pairs where implemented value
                     types are \"cumulative\", \"actual\" and \"date\"; \"date\"
                     variables are used to aggregate data and only one is used
        - current: current period timestamp formatted according to fmt
        - fmt: datetime format, it determines how to aggregate data, e.g.
               * \"%Y-%m-%d\" will generate a report considering previous and
                 current day as consecutive periods (i.e. a day report),
               * \"%Y-%m\" will consider previous and current month as
                 consecutive periods (i.e. a month report)
        - area: area passed to get_df method
        - errors: set if trying to continue execution or raise an
                  exception when some condition is not respected;
                  implemented values are \"strict\" and \"ignore\"

        Returns:
        report
        """

        df = self.get_df(key, area=area)

        self._logger.debug(
            f"Generating report \"{current}\" for dataframe \"{key}\"" + \
            f", area = \"{area}\"" if area != None else ""
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

        self._logger.debug(f"Returning report: {report}")

        return report
