"""
Esegue le interrogazioni di sql/kpi.sql sul data warehouse e ne stampa i risultati.

Le query sono identificate da una riga "-- name: <nome>"; la funzione
carica_query() è riutilizzata anche dalla dashboard.

Uso:
    python src/kpi.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
FILE_DB = RADICE / "data" / "warehouse" / "tecnosolution.db"
FILE_KPI = RADICE / "sql" / "kpi.sql"


def carica_query(percorso=FILE_KPI):
    """Restituisce un dizionario {nome: testo SQL} letto dal file delle query."""
    query, nome, righe = {}, None, []
    for riga in Path(percorso).read_text(encoding="utf-8").splitlines():
        if riga.strip().startswith("-- name:"):
            if nome:
                query[nome] = "\n".join(righe).strip()
            nome, righe = riga.split(":", 1)[1].strip(), []
        elif nome:
            righe.append(riga)
    if nome:
        query[nome] = "\n".join(righe).strip()
    return query


def main():
    if not FILE_DB.exists():
        raise SystemExit("Database non trovato: eseguire prima  python src/etl.py")
    pd.set_option("display.width", 140)
    with sqlite3.connect(FILE_DB) as con:
        for nome, sql in carica_query().items():
            print(f"\n=== {nome} ===")
            print(pd.read_sql_query(sql, con).to_string(index=False))


if __name__ == "__main__":
    main()
