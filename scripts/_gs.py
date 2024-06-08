from pathlib import Path
import time

import gspread

from scripts._dir import PARSER_OOT


SPREADSHEET_ID = "1SSFQgfg-EFqfRzdKnoyRZIB7t6cwc_4MyseFXRdOSqs"

gc: gspread.Client | None = None
workbook: gspread.Spreadsheet | None = None


def get_worksheet(name: str):
    global gc, workbook
    if gc is None:
        gc = gspread.oauth(
            credentials_filename=PARSER_OOT / "secrets/google-credentials.json",
            authorized_user_filename=PARSER_OOT / "secrets/google-token.json",
        )
    if workbook is None:
        workbook = gc.open_by_key(SPREADSHEET_ID)

    try:
        time.sleep(1)
        return workbook.worksheet(name)
    except gspread.WorksheetNotFound:
        return workbook.add_worksheet(name, 1, 1)
