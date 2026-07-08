from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["User", "Target Classification"]


def read_sap_user_export(file_path: Path) -> list[dict[str, str | None]]:
    dataframe = pd.read_excel(file_path, sheet_name="Data", engine="openpyxl")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"Missing required Excel column(s): {missing}")

    users = dataframe[REQUIRED_COLUMNS].copy()
    users = users.rename(
        columns={
            "User": "username",
            "Target Classification": "category",
        }
    )

    users["username"] = users["username"].astype("string").str.strip()
    users["category"] = users["category"].astype("string").str.strip()
    users = users.dropna(subset=["username"])
    users = users[users["username"] != ""]
    users = users.drop_duplicates(subset=["username"], keep="first")
    users = users.sort_values("username")

    records = users.where(pd.notna(users), None).to_dict(orient="records")
    return [
        {
            "username": str(record["username"]),
            "category": record["category"] if record["category"] is not None else None,
        }
        for record in records
    ]
