"""
ETL (Estrazione, Trasformazione, Caricamento) di TecnoSolution.

1. ESTRAZIONE      legge i quattro CSV di data/raw/ come testo, senza fidarsi dei tipi
2. TRASFORMAZIONE  pulisce e uniforma i dati:
                     - spazi e maiuscole incoerenti -> valori canonici
                     - date in formati diversi -> AAAA-MM-GG / AAAA-MM-GG HH:MM
                     - virgola decimale -> punto
                     - righe duplicate e codici ripetuti -> rimossi
                     - importi mancanti -> 0 se annullata, altrimenti mediana della categoria
                     - controlli di coerenza (chiavi esterne, stato vs tempo di erogazione)
                   e costruisce le dimensioni (con chiavi surrogate) e la tabella dei fatti
3. CARICAMENTO     ricrea il database SQLite data/warehouse/tecnosolution.db con lo
                   schema di sql/schema.sql e vi inserisce i dati

Ogni correzione viene contata e riportata nel log data/warehouse/log_etl.txt.

Uso:
    python src/etl.py
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
DIR_RAW = RADICE / "data" / "raw"
DIR_DW = RADICE / "data" / "warehouse"
FILE_DB = DIR_DW / "tecnosolution.db"
FILE_SCHEMA = RADICE / "sql" / "schema.sql"
FILE_LOG = DIR_DW / "log_etl.txt"

SLA_ORE = 48  # oltre questa durata un intervento è considerato in ritardo

# Vocabolari di riferimento: i soli valori ammessi nel data warehouse
ZONE = ["Palermo", "Catania", "Messina", "Siracusa", "Trapani",
        "Agrigento", "Ragusa", "Caltanissetta", "Enna"]
CATEGORIE = ["Riparazione PC e hardware", "Smartphone e tablet", "Reti e Wi-Fi",
             "Installazione e config. software", "Recupero dati", "Stampanti e periferiche"]
TIPI_ATTIVITA = ["Tecnico hardware", "Tecnico mobile", "Tecnico reti", "Tecnico software"]
STATI = ["Completata", "In ritardo", "Annullata"]

NOMI_MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
             "agosto", "settembre", "ottobre", "novembre", "dicembre"]
NOMI_GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


class Log:
    """Raccoglie i messaggi del processo e li salva su file alla fine."""

    def __init__(self):
        self.righe = [f"ETL TecnoSolution – esecuzione del {datetime.now():%d/%m/%Y %H:%M}", ""]

    def __call__(self, msg):
        print(msg)
        self.righe.append(msg)

    def salva(self, percorso):
        percorso.write_text("\n".join(self.righe) + "\n", encoding="utf-8")


log = Log()


# ---------------------------------------------------------------------------
# 1. ESTRAZIONE
# ---------------------------------------------------------------------------

def estrai():
    tabelle = {}
    for nome in ("clienti", "fornitori", "operatori", "richieste"):
        df = pd.read_csv(DIR_RAW / f"{nome}.csv", dtype=str, keep_default_na=False)
        tabelle[nome] = df
        log(f"[E] {nome:<10} letti {len(df):>4} record")
    return tabelle


# ---------------------------------------------------------------------------
# 2. TRASFORMAZIONE – funzioni di pulizia riutilizzabili
# ---------------------------------------------------------------------------

def chiave(testo):
    """Forma normalizzata per il confronto: niente spazi superflui, minuscolo."""
    return " ".join(str(testo).split()).casefold()


def uniforma(serie, ammessi, nome_campo, tabella):
    """Riporta ogni valore alla grafia canonica del vocabolario `ammessi`."""
    mappa = {chiave(v): v for v in ammessi}
    pulita = serie.map(lambda v: mappa.get(chiave(v)))
    corretti = int(((serie != pulita) & pulita.notna()).sum())
    sconosciuti = int(pulita.isna().sum())
    if corretti:
        log(f"[T] {tabella}.{nome_campo}: {corretti} valori uniformati (maiuscole/spazi)")
    if sconosciuti:
        log(f"[T] {tabella}.{nome_campo}: {sconosciuti} valori non riconosciuti -> righe scartate")
    return pulita


def converti_date(serie, nome_campo, tabella):
    """Accetta AAAA-MM-GG[ HH:MM] e GG/MM/AAAA[ HH:MM]; restituisce datetime."""
    s = serie.str.strip()
    risultato = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    formati = ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"]
    for fmt in formati:
        mancanti = risultato.isna()
        risultato[mancanti] = pd.to_datetime(s[mancanti], format=fmt, errors="coerce")
    italiane = int(s.str.contains("/", regex=False).sum())
    if italiane:
        log(f"[T] {tabella}.{nome_campo}: {italiane} date in formato GG/MM/AAAA convertite")
    non_valide = int(risultato.isna().sum())
    if non_valide:
        log(f"[T] {tabella}.{nome_campo}: {non_valide} date non interpretabili -> righe scartate")
    return risultato


def converti_numeri(serie, nome_campo, tabella):
    """Gestisce la virgola decimale e le celle vuote."""
    s = serie.str.strip()
    con_virgola = int(s.str.contains(",", regex=False).sum())
    if con_virgola:
        log(f"[T] {tabella}.{nome_campo}: {con_virgola} numeri con virgola decimale corretti")
    return pd.to_numeric(s.str.replace(",", ".", regex=False).replace("", None), errors="coerce")


def rimuovi_duplicati(df, colonna_id, tabella):
    prima = len(df)
    df = df.drop_duplicates()
    esatti = prima - len(df)
    prima = len(df)
    df = df.drop_duplicates(subset=colonna_id, keep="first")
    stesso_id = prima - len(df)
    if esatti:
        log(f"[T] {tabella}: {esatti} righe duplicate rimosse")
    if stesso_id:
        log(f"[T] {tabella}: {stesso_id} righe con {colonna_id} ripetuto rimosse")
    return df


def scarta_incompleti(df, colonne, tabella):
    prima = len(df)
    df = df.dropna(subset=colonne)
    if prima - len(df):
        log(f"[T] {tabella}: {prima - len(df)} righe scartate perché incomplete")
    return df


# ---------------------------------------------------------------------------
# 2. TRASFORMAZIONE – tabelle
# ---------------------------------------------------------------------------

def trasforma_clienti(df):
    t = "clienti"
    df = df.apply(lambda c: c.str.strip())
    df["zona"] = uniforma(df["zona"], ZONE, "zona", t)
    df["data_iscrizione"] = converti_date(df["data_iscrizione"], "data_iscrizione", t)
    df = rimuovi_duplicati(df, "id_cliente", t)
    df = scarta_incompleti(df, ["id_cliente", "zona", "data_iscrizione"], t)
    df["anno_mese_iscrizione"] = df["data_iscrizione"].dt.strftime("%Y-%m")
    df["data_iscrizione"] = df["data_iscrizione"].dt.strftime("%Y-%m-%d")
    return df.sort_values("id_cliente").reset_index(drop=True)


def trasforma_fornitori(df):
    t = "fornitori"
    df = df.apply(lambda c: c.str.strip())
    df["nome"] = df["nome"].map(lambda v: " ".join(v.split()))
    df["zona"] = uniforma(df["zona"], ZONE, "zona", t)
    df["categoria_servizio"] = uniforma(df["categoria_servizio"], CATEGORIE, "categoria_servizio", t)
    df = rimuovi_duplicati(df, "id_fornitore", t)
    df = scarta_incompleti(df, ["id_fornitore", "nome", "zona", "categoria_servizio"], t)
    return df.sort_values("id_fornitore").reset_index(drop=True)


def trasforma_operatori(df):
    t = "operatori"
    df = df.apply(lambda c: c.str.strip())
    df["zona"] = uniforma(df["zona"], ZONE, "zona", t)
    df["tipo_attivita"] = uniforma(df["tipo_attivita"], TIPI_ATTIVITA, "tipo_attivita", t)
    df = rimuovi_duplicati(df, "id_operatore", t)
    df = scarta_incompleti(df, ["id_operatore", "zona", "tipo_attivita"], t)
    return df.sort_values("id_operatore").reset_index(drop=True)


def trasforma_richieste(df, clienti, fornitori, operatori):
    t = "richieste"
    df = df.apply(lambda c: c.str.strip())
    df["stato"] = uniforma(df["stato"], STATI, "stato", t)
    df["data_ora"] = converti_date(df["data_ora"], "data_ora", t)
    df["importo"] = converti_numeri(df["importo"], "importo", t)
    df["tempo_erogazione_ore"] = converti_numeri(df["tempo_erogazione_ore"],
                                                 "tempo_erogazione_ore", t)
    df = rimuovi_duplicati(df, "id_richiesta", t)
    df = scarta_incompleti(df, ["id_richiesta", "id_cliente", "id_fornitore",
                                "id_operatore", "data_ora", "stato"], t)

    # Integrità referenziale: ogni richiesta deve puntare a record esistenti
    for col, dim in [("id_cliente", clienti), ("id_fornitore", fornitori),
                     ("id_operatore", operatori)]:
        orfane = ~df[col].isin(dim[col])
        if orfane.any():
            log(f"[T] {t}: {int(orfane.sum())} righe con {col} inesistente -> scartate")
            df = df[~orfane]

    # Importi mancanti
    annullata = df["stato"] == "Annullata"
    df["importo_stimato"] = 0
    manc_annullate = annullata & df["importo"].isna()
    df.loc[manc_annullate, "importo"] = 0.0
    manc_erogate = ~annullata & df["importo"].isna()
    if manc_erogate.any():
        categoria = df["id_fornitore"].map(fornitori.set_index("id_fornitore")["categoria_servizio"])
        mediane = df[~annullata & df["importo"].notna()].groupby(categoria)["importo"].median()
        df.loc[manc_erogate, "importo"] = categoria[manc_erogate].map(mediane).round(2)
        df.loc[manc_erogate, "importo_stimato"] = 1
        log(f"[T] {t}.importo: {int(manc_erogate.sum())} importi mancanti stimati con la "
            f"mediana della categoria (segnalati con importo_stimato = 1)")
    if manc_annullate.any():
        log(f"[T] {t}.importo: {int(manc_annullate.sum())} importi mancanti di richieste "
            f"annullate impostati a 0")

    # Coerenza stato / tempo di erogazione rispetto alla soglia SLA
    da_ritardo = (df["stato"] == "Completata") & (df["tempo_erogazione_ore"] > SLA_ORE)
    if da_ritardo.any():
        df.loc[da_ritardo, "stato"] = "In ritardo"
        log(f"[T] {t}: {int(da_ritardo.sum())} richieste oltre {SLA_ORE}h riclassificate 'In ritardo'")
    annullata = df["stato"] == "Annullata"
    df.loc[annullata, "tempo_erogazione_ore"] = None

    # Controllo informativo: richiesta precedente all'iscrizione del cliente
    iscr = pd.to_datetime(df["id_cliente"].map(clienti.set_index("id_cliente")["data_iscrizione"]))
    anomale = int((df["data_ora"].dt.normalize() < iscr).sum())
    log(f"[T] {t}: {anomale} richieste precedenti alla data di iscrizione del cliente")

    df["flag_annullata"] = annullata.astype(int)
    df["flag_ritardo"] = (df["stato"] == "In ritardo").astype(int)
    return df.sort_values("data_ora").reset_index(drop=True)


def costruisci_dim_tempo(date):
    """Calendario completo (tutti i giorni) dal primo all'ultimo giorno dei dati."""
    giorni = pd.date_range(date.min().normalize(), date.max().normalize(), freq="D")
    iso = giorni.isocalendar()
    return pd.DataFrame({
        "id_tempo": giorni.strftime("%Y%m%d").astype(int),
        "data": giorni.strftime("%Y-%m-%d"),
        "anno": giorni.year,
        "trimestre": giorni.quarter,
        "mese": giorni.month,
        "nome_mese": [NOMI_MESI[m - 1] for m in giorni.month],
        "anno_mese": giorni.strftime("%Y-%m"),
        "settimana_iso": iso["week"].to_numpy(),
        "giorno_settimana": giorni.dayofweek + 1,
        "nome_giorno": [NOMI_GIORNI[d] for d in giorni.dayofweek],
        "weekend": (giorni.dayofweek >= 5).astype(int),
    })


def aggiungi_chiave_surrogata(df, nome):
    df = df.copy()
    df.insert(0, nome, range(1, len(df) + 1))
    return df


# ---------------------------------------------------------------------------
# 3. CARICAMENTO
# ---------------------------------------------------------------------------

def carica(dim_cliente, dim_fornitore, dim_operatore, dim_tempo, fatto):
    DIR_DW.mkdir(parents=True, exist_ok=True)
    if FILE_DB.exists():
        FILE_DB.unlink()  # caricamento completo: il warehouse viene ricostruito da zero
    con = sqlite3.connect(FILE_DB)
    try:
        con.executescript(FILE_SCHEMA.read_text(encoding="utf-8"))
        for nome, df in [("dim_cliente", dim_cliente), ("dim_fornitore", dim_fornitore),
                         ("dim_operatore", dim_operatore), ("dim_tempo", dim_tempo),
                         ("fatto_richieste", fatto)]:
            df.to_sql(nome, con, if_exists="append", index=False)
            log(f"[L] {nome:<16} caricate {len(df):>4} righe")
        con.commit()
        violazioni = con.execute("PRAGMA foreign_key_check").fetchall()
        log(f"[L] controllo chiavi esterne: {'OK' if not violazioni else violazioni}")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    raw = estrai()
    log("")

    clienti = trasforma_clienti(raw["clienti"])
    fornitori = trasforma_fornitori(raw["fornitori"])
    operatori = trasforma_operatori(raw["operatori"])
    richieste = trasforma_richieste(raw["richieste"], clienti, fornitori, operatori)
    log("")

    dim_cliente = aggiungi_chiave_surrogata(clienti, "sk_cliente")
    dim_fornitore = aggiungi_chiave_surrogata(fornitori, "sk_fornitore")
    dim_operatore = aggiungi_chiave_surrogata(operatori, "sk_operatore")
    dim_tempo = costruisci_dim_tempo(richieste["data_ora"])

    fatto = pd.DataFrame({
        "id_richiesta": richieste["id_richiesta"],
        "sk_cliente": richieste["id_cliente"].map(dim_cliente.set_index("id_cliente")["sk_cliente"]),
        "sk_fornitore": richieste["id_fornitore"].map(
            dim_fornitore.set_index("id_fornitore")["sk_fornitore"]),
        "sk_operatore": richieste["id_operatore"].map(
            dim_operatore.set_index("id_operatore")["sk_operatore"]),
        "id_tempo": richieste["data_ora"].dt.strftime("%Y%m%d").astype(int),
        "ora": richieste["data_ora"].dt.hour,
        "stato": richieste["stato"],
        "importo": richieste["importo"].round(2),
        "importo_stimato": richieste["importo_stimato"],
        "tempo_erogazione_ore": richieste["tempo_erogazione_ore"],
        "flag_annullata": richieste["flag_annullata"],
        "flag_ritardo": richieste["flag_ritardo"],
    })

    carica(dim_cliente, dim_fornitore, dim_operatore, dim_tempo, fatto)
    log("")
    log(f"Data warehouse creato: {FILE_DB.relative_to(RADICE)}")
    log.salva(FILE_LOG)


if __name__ == "__main__":
    main()
