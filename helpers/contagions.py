
"""Covid-19 contagions data module."""


from .database import RemoteResource, LocalResource, Report, BaseDatabase

from logging import getLogger
from typing import Dict, Optional
from pathlib import Path
import pandas as pd


LOGGER = getLogger(__name__)


class Database(BaseDatabase):
    """BaseDatabase derived class for Covid-19 contagions data."""

    # report variables
    _variables: Dict[str,str] = {
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
    }


    def __init__(
        self, remote: RemoteResource = {
            "base_url": "https://raw.githubusercontent.com",
            "repo": "pcm-dpc/COVID-19",
            "branch": "master",
            "files": {
                "national": "dati-andamento-nazionale/"
                            "dpc-covid19-ita-andamento-nazionale.csv",
                "regional": "dati-regioni/dpc-covid19-ita-regioni.csv"
            }
        },
        local: dict = {
            "dir": Path("share/contagions"),
            "files": {
                "national": "dpc-covid19-ita-andamento-nazionale.csv",
                "regional": "dpc-covid19-ita-regioni.csv"
            }
        }
    ):
        """Parameters documented in BaseDatabase.__init__"""

        BaseDatabase.__init__(self, remote=remote, local=local)


    def get_df(
        self, key: str, /, area: Optional[str] = None, errors: str = "strict",
        **kwargs
    ) -> Optional[pd.DataFrame]:
        """Parameters documented in BaseDatabase.get_df."""

        return BaseDatabase.get_df(
            self, key, area=area, area_column="denominazione_regione",
            errors=errors, **kwargs
        )


    def get_report(
        self, key: str, /, current: str, fmt: str = "%Y-%m-%d",
        area: Optional[str] = None, errors="strict"
    ) -> Report:
        """Parameters documented in BaseDatabase.get_report"""

        return BaseDatabase.get_report(
            self, key, variables=self._variables, current=current, fmt=fmt,
            area=area, errors=errors
        )
