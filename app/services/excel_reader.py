from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
import olefile
from openpyxl.utils.exceptions import InvalidFileException
from xlrd.biffh import XLRDError


REQUIRED_COLUMNS = ["User", "Target Classification"]
OPTIONAL_COLUMN_MAP = {
    "ID": "user_id",
    "Full Name": "full_name",
}
XLSX_SIGNATURE = b"PK"
XLS_SIGNATURE = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"


def detect_excel_engine(file_path: Path) -> str:
    with file_path.open("rb") as file:
        signature = file.read(8)

    if signature.startswith(XLSX_SIGNATURE):
        return "openpyxl"

    if signature == XLS_SIGNATURE:
        if olefile.isOleFile(file_path):
            ole = olefile.OleFileIO(file_path)
            streams = {"/".join(stream) for stream in ole.listdir(streams=True, storages=True)}
            if "EncryptedPackage" in streams:
                raise ValueError(
                    "The SAP export is encrypted or protected. Open it in Excel and save "
                    "a normal unprotected .xlsx workbook before uploading."
                )
        return "xlrd"

    raise ValueError(
        "The uploaded file is not a valid Excel workbook. "
        "Export the SAP file as .xlsx or .xls and try again."
    )


def read_sap_user_export(file_path: Path) -> list[dict[str, str | None]]:
    try:
        engine = detect_excel_engine(file_path)
        dataframe = pd.read_excel(file_path, sheet_name="Data", engine=engine)
    except BadZipFile as error:
        raise ValueError(
            "The uploaded file is not a valid .xlsx Excel workbook. "
            "Export the SAP file as a real Excel .xlsx file and try again."
        ) from error
    except InvalidFileException as error:
        raise ValueError(str(error)) from error
    except ImportError as error:
        raise ValueError(
            "This SAP export is an old Excel .xls workbook. Install the xlrd package "
            "or save the file again as a real .xlsx workbook."
        ) from error
    except XLRDError as error:
        raise ValueError(
            "The uploaded file is not a readable Excel workbook. Open it in Excel and save "
            "a normal unprotected .xlsx workbook before uploading."
        ) from error

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required Excel column(s): {missing}")

    selected_columns = REQUIRED_COLUMNS + [
        column for column in OPTIONAL_COLUMN_MAP if column in dataframe.columns
    ]
    users = dataframe[selected_columns].copy()
    users = users.rename(
        columns={
            "User": "username",
            "Target Classification": "category",
            **OPTIONAL_COLUMN_MAP,
        }
    )

    users["username"] = users["username"].astype("string").str.strip()
    users["category"] = users["category"].astype("string").str.strip()
    for column in OPTIONAL_COLUMN_MAP.values():
        if column not in users.columns:
            users[column] = None
        users[column] = users[column].astype("string").str.strip()

    users = users.dropna(subset=["username"])
    users = users[users["username"] != ""]
    users = users.drop_duplicates(subset=["username"], keep="first")
    users = users.sort_values("username")

    records = users.where(pd.notna(users), None).to_dict(orient="records")
    return [
        {
            "username": str(record["username"]),
            "user_id": record["user_id"] if record["user_id"] is not None else None,
            "full_name": record["full_name"] if record["full_name"] is not None else None,
            "category": record["category"] if record["category"] is not None else None,
        }
        for record in records
    ]
