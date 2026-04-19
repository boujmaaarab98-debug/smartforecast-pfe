import pandas as pd

SHEET_ID = "1DNmM76FfZRtucCMEB-If0t1EEV-lPRn70pl9yP2ooeM"

def build_url(sheet_name):
    return f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={sheet_name}"

def load_sheet(sheet_name):
    url = build_url(sheet_name)
    return pd.read_csv(url)

def load_all_data():
    return {
        "param": load_sheet("Param"),
        "mrp": load_sheet("MRP"),
        "fournisseurs": load_sheet("Fournisseurs"),
        "conso": load_sheet("Conso"),
    }
