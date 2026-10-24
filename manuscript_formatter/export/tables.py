"""Táblázat-előkészítés: számok felismerése és kerekítése a sablon szerint."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

_NUMBER_RE = re.compile(r"^[+\-−]?(\d{1,3}([ ,  ]\d{3})+|\d+)?([.,]\d+)?([eE][+\-]?\d+)?$")


def parse_number(value: Any) -> Any:
    """Szöveges szám → float/int (tizedesvessző, ezres tagolás, unicode mínusz kezelése).

    Ami nem egyértelműen szám, azt változatlanul adja vissza.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or not _NUMBER_RE.match(text) or not any(c.isdigit() for c in text):
        return value
    text = text.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(",", "")  # 1,234.5
    elif text.count(",") == 1 and len(text.split(",")[1]) != 3:
        text = text.replace(",", ".")  # 3,14 (tizedesvessző)
    elif text.count(",") >= 1:
        text = text.replace(",", "")  # 1,234 vagy 1,234,567
    try:
        number = float(text)
    except ValueError:
        return value
    if number.is_integer() and "." not in text and "e" not in text.lower():
        return int(number)
    return number


def typed_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Cellánként számmá alakított másolat (objektum típusú oszlopokkal)."""
    result = df.copy().astype(object)
    for column in result.columns:
        values = [parse_number(v) for v in result[column]]
        result[column] = pd.Series(values, index=result.index, dtype=object)
    return result


def numeric_columns(df: pd.DataFrame) -> list[bool]:
    """Oszloponként: igaz, ha a nem üres cellák mind számok."""
    flags = []
    for column in range(df.shape[1]):
        values = [v for v in df.iloc[:, column] if not (isinstance(v, str) and not v.strip())]
        flags.append(bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                          for v in values))
    return flags


def format_number(value: Any, decimal_places: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "" if value is None else str(value)
    if decimal_places >= 0 and isinstance(value, float):
        return f"{value:.{decimal_places}f}"
    return str(value)
