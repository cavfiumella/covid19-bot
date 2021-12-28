
"""Covid-19 vaccination data module."""


from .database import RemoteResource, LocalResource, Report, BaseDatabase

from logging import getLogger
from typing import Dict, Optional
from pathlib import Path
from urllib.request import urlopen
import json
import pandas as pd


LOGGER = getLogger(__name__)


class Database(BaseDatabase):
    """BaseDatabase derived class for Covid-19 vaccination data."""

    # columns to use for dataframes in report generation
    _variables: Dict[str,str] = {
        "deliveries": {
            "data_consegna": "date",
            "numero_dosi": "actual"
        },
        "doses": {
            "data_somministrazione": "date",
            "prima_dose": "actual",
            "seconda_dose": "actual",
            "pregressa_infezione": "actual",
            "dose_addizionale_booster": "actual"
        }
    }


    def _dataset_update(
        self, s: str, /, tz: str = "Europe/Rome"
    ) -> pd.Timestamp:
        """Timestamp of last dataset update.

        Parameters:
        - s: json encoded string containing dataset update in
             \"ultimo_aggiornamento\"
        - tz: timestamps timezone

        Returns:
        timestamp
        """

        t = pd.Timestamp(json.loads(s)["ultimo_aggiornamento"], tz=tz)

        self._logger.debug(f"Dataset update: \"{t}\"")

        return t


    def local_dataset_update(self, tz: str = "Europe/Rome") -> pd.Timestamp:
        """Timestamp of local dataset update.

        Parameters:
        - tz: timestamps timezone

        Returns:
        timestamp
        """

        with open(self._get_local_path("update")) as file:
            t = self._dataset_update(file.read(), tz=tz)

        self._logger.debug(f"Local dataset update: \"{t}\"")

        return t


    def remote_dataset_update(self, tz: str = "Europe/Rome") -> pd.Timestamp:
        """Timestamp of remote dataset update.

        Parameters:
        - tz: timestamps timezone

        Returns:
        timestamp
        """

        t = self._dataset_update(
            urlopen(self._get_remote_path("update")).read(), tz=tz
        )

        self._logger.debug(f"Remote dataset update: \"{t}\"")

        return t


    def update(self) -> None:
        """Update local dataset if it is missing some file or remote dataset is
        newer.
        """

        # get keys of missing or old files
        keys = []
        for key in self._remote["files"]:
            if not self._get_local_path(key).exists() or \
            self.remote_dataset_update() > self.local_dataset_update():
                keys += [key]

        # update
        if len(keys) != 0:
            BaseDatabase.update(self, *keys)


    def __init__(
        self, remote: dict = {
            "base_url": "https://raw.githubusercontent.com",
            "repo": "italia/covid19-opendata-vaccini",
            "branch": "master",
            "files": {
                "deliveries": "dati/consegne-vaccini-latest.csv",
                "doses": "dati/somministrazioni-vaccini-latest.csv",
                "people": "dati/platea.csv",
                "people_booster": "dati/platea-dose-addizionale-booster.csv",
                "update": "dati/last-update-dataset.json"
            }
        },
        local: dict = {
            "dir": Path("share/vaccines"),
            "files": {
                "deliveries": "consegne-vaccini-latest.csv",
                "doses": "somministrazioni-vaccini-latest.csv",
                "people": "platea.csv",
                "people_booster": "platea-dose-addizionale-booster.csv",
                "update": "last-update-dataset.json"
            }
        }
    ):
        """Parameters documented in BaseDatabase.__init__"""

        BaseDatabase.__init__(self, remote=remote, local=local)


    def get_report(
        self, key: str, /, current: str, fmt: str = "%Y-%m-%d",
        area: Optional[str] = None, errors="strict"
    ) -> Report:
        """Parameters documented in BaseDatabase.get_report"""

        return BaseDatabase.get_report(
            self, key, variables=self._variables[key], current=current, fmt=fmt,
            area=area, errors=errors
        )


    def get_df(
        self, key: str, /, area: Optional[str] = None, errors: str = "strict",
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """Parameters documented in BaseDatabase.get_df."""

        return BaseDatabase.get_df(
            self, key, area=area, area_column="nome_area", errors=errors,
            **kwargs
        )
