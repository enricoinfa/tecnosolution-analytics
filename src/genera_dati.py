"""
Generatore di dati sintetici per TecnoSolution
(startup inventata di assistenza tecnica IT on-demand nei capoluoghi siciliani).

Crea quattro file CSV in data/raw/:
    clienti.csv, fornitori.csv, operatori.csv, richieste.csv

I dati sono completamente inventati e non contengono informazioni personali:
clienti e operatori sono identificati solo da un codice.

Per mettere alla prova la fase di pulizia dell'ETL, una piccola quota di righe
viene volutamente "sporcata" (maiuscole/spazi incoerenti, formati di data diversi,
virgola decimale, valori mancanti, righe duplicate). La quota si regola con --sporcizia.

Uso:
    python src/genera_dati.py
    python src/genera_dati.py --seed 7 --richieste 600 --sporcizia 0
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Parametri di dominio
# ---------------------------------------------------------------------------

# Capoluoghi siciliani con peso indicativo proporzionale alla popolazione
ZONE = {
    "Palermo": 0.25,
    "Catania": 0.22,
    "Messina": 0.12,
    "Siracusa": 0.08,
    "Trapani": 0.07,
    "Agrigento": 0.07,
    "Ragusa": 0.07,
    "Caltanissetta": 0.06,
    "Enna": 0.06,
}

# Categoria di servizio -> (peso domanda, importo medio €, tempo medio di erogazione in ore,
#                           tipo di operatore che la svolge)
CATEGORIE = {
    "Riparazione PC e hardware":        (0.26, 85.0, 26.0, "Tecnico hardware"),
    "Smartphone e tablet":              (0.22, 65.0, 20.0, "Tecnico mobile"),
    "Reti e Wi-Fi":                     (0.16, 95.0, 22.0, "Tecnico reti"),
    "Installazione e config. software": (0.18, 45.0, 10.0, "Tecnico software"),
    "Recupero dati":                    (0.08, 160.0, 48.0, "Tecnico hardware"),
    "Stampanti e periferiche":          (0.10, 55.0, 18.0, "Tecnico hardware"),
}

TIPI_OPERATORE = ["Tecnico hardware", "Tecnico mobile", "Tecnico reti", "Tecnico software"]

# Ora del giorno: picchi a metà mattina e nel tardo pomeriggio
PESI_ORA = np.array(
    [0, 0, 0, 0, 0, 0, 0, 1, 4, 8, 10, 10, 8, 5, 4, 6, 8, 9, 9, 7, 4, 2, 1, 0], dtype=float
)
# Giorno della settimana (lun..dom): lunedì più carico, domenica minimo
PESI_GIORNO = np.array([1.35, 1.15, 1.05, 1.05, 1.10, 0.75, 0.35])

# Soglia di servizio (SLA): oltre questa durata la richiesta è considerata in ritardo
SLA_ORE = 48

PREFISSI_NOMI = ["Info", "Tecno", "Digi", "Net", "PC", "Smart", "Byte", "Data", "Micro", "Cyber",
                 "Help", "Pronto", "Logic", "Click", "Giga"]
SUFFISSI_NOMI = ["Point", "Lab", "Service", "Store", "Center", "Fix", "Shop", "System", "Solution",
                 "Assist", "Tech", "Planet", "Market", "World", "Express"]


# ---------------------------------------------------------------------------
# Generazione delle singole tabelle
# ---------------------------------------------------------------------------

def scegli_zone(rng, n):
    return rng.choice(list(ZONE), size=n, p=list(ZONE.values()))


def genera_clienti(rng, n, inizio, fine):
    """Clienti con data di iscrizione crescente nel tempo (la startup si espande)."""
    giorni_totali = (fine - inizio).days
    # distribuzione sbilanciata verso la fine del periodo: più iscrizioni man mano che cresce
    frazioni = rng.beta(1.6, 1.0, size=n)
    frazioni[0] = 0.0  # il primo cliente si iscrive il giorno del lancio del servizio
    date = inizio + pd.to_timedelta(np.floor(frazioni * giorni_totali), unit="D")
    df = pd.DataFrame({
        "id_cliente": [f"C{i:04d}" for i in range(1, n + 1)],
        "zona": scegli_zone(rng, n),
        "data_iscrizione": date,
    })
    return df.sort_values("data_iscrizione").reset_index(drop=True).assign(
        id_cliente=[f"C{i:04d}" for i in range(1, n + 1)]
    )


def genera_fornitori(rng, n):
    nomi_usati = set()
    righe = []
    categorie = list(CATEGORIE)
    for i in range(1, n + 1):
        zona = scegli_zone(rng, 1)[0]
        while True:
            nome = f"{rng.choice(PREFISSI_NOMI)}{rng.choice(SUFFISSI_NOMI)} {zona}"
            if nome not in nomi_usati:
                break
            nome = f"{nome} {rng.integers(2, 99)}"
            if nome not in nomi_usati:
                break
        nomi_usati.add(nome)
        righe.append({
            "id_fornitore": f"F{i:03d}",
            "nome": nome,
            "categoria_servizio": categorie[i % len(categorie)],  # copertura di tutte le categorie
            "zona": zona,
        })
    df = pd.DataFrame(righe)
    # rimescolo le categorie per non avere un pattern regolare
    df["categoria_servizio"] = rng.permutation(df["categoria_servizio"].to_numpy())
    return df


def genera_operatori(rng, n):
    return pd.DataFrame({
        "id_operatore": [f"O{i:03d}" for i in range(1, n + 1)],
        "zona": scegli_zone(rng, n),
        "tipo_attivita": rng.choice(TIPI_OPERATORE, size=n, p=[0.40, 0.20, 0.20, 0.20]),
    })


def genera_istanti(rng, n, inizio, fine):
    """Date e ore delle richieste con crescita nel tempo e stagionalità settimanale/oraria."""
    giorni = pd.date_range(inizio, fine - pd.Timedelta(days=1), freq="D")
    crescita = np.linspace(0.5, 1.6, len(giorni))          # domanda in aumento
    peso_giorno = PESI_GIORNO[giorni.dayofweek.to_numpy()]
    p = crescita * peso_giorno
    p = p / p.sum()
    giorni_scelti = rng.choice(len(giorni), size=n, p=p)
    ore = rng.choice(24, size=n, p=PESI_ORA / PESI_ORA.sum())
    minuti = rng.integers(0, 60, size=n)
    istanti = (giorni[giorni_scelti]
               + pd.to_timedelta(ore, unit="h")
               + pd.to_timedelta(minuti, unit="m"))
    return pd.Series(np.sort(istanti.to_numpy()))


def genera_richieste(rng, n, clienti, fornitori, operatori, inizio, fine,
                     quota_annullate, quota_ritardi):
    istanti = genera_istanti(rng, n, inizio, fine)

    # "fedeltà" di ogni cliente: pochi clienti molto fedeli, molti occasionali
    fedelta = rng.lognormal(mean=0.0, sigma=1.0, size=len(clienti))
    iscrizioni = clienti["data_iscrizione"].to_numpy()

    nomi_cat = list(CATEGORIE)
    pesi_cat = np.array([v[0] for v in CATEGORIE.values()])
    pesi_cat = pesi_cat / pesi_cat.sum()

    righe = []
    for i, ts in enumerate(istanti, start=1):
        # il cliente deve essere già iscritto al momento della richiesta
        idx_validi = np.flatnonzero(iscrizioni <= np.datetime64(ts))
        w = fedelta[idx_validi]
        cli = clienti.iloc[rng.choice(idx_validi, p=w / w.sum())]

        categoria = rng.choice(nomi_cat, p=pesi_cat)
        _, importo_medio, ore_medie, tipo_op = CATEGORIE[categoria]

        # fornitore della stessa categoria, preferibilmente nella stessa zona
        f_cand = fornitori[(fornitori["categoria_servizio"] == categoria)
                           & (fornitori["zona"] == cli["zona"])]
        if f_cand.empty:
            f_cand = fornitori[fornitori["categoria_servizio"] == categoria]
        fornitore = f_cand.iloc[rng.integers(len(f_cand))]

        # operatore con la competenza giusta, preferibilmente nella stessa zona
        o_cand = operatori[(operatori["tipo_attivita"] == tipo_op)
                           & (operatori["zona"] == cli["zona"])]
        if o_cand.empty:
            o_cand = operatori[operatori["tipo_attivita"] == tipo_op]
        operatore = o_cand.iloc[rng.integers(len(o_cand))]

        u = rng.random()
        if u < quota_annullate:
            stato = "Annullata"
            importo = 0.0
            tempo_ore = np.nan
        else:
            importo = round(max(15.0, rng.normal(importo_medio, importo_medio * 0.30)), 2)
            if u < quota_annullate + quota_ritardi:
                stato = "In ritardo"
                tempo_ore = SLA_ORE + rng.gamma(shape=2.0, scale=12.0)
            else:
                stato = "Completata"
                # durata entro la soglia SLA (si ripete l'estrazione finché è sotto soglia)
                tempo_ore = SLA_ORE
                while tempo_ore >= SLA_ORE - 0.1:
                    tempo_ore = rng.gamma(shape=2.0, scale=ore_medie / 2.0) + 0.5

        righe.append({
            "id_richiesta": f"R{i:05d}",
            "id_cliente": cli["id_cliente"],
            "id_fornitore": fornitore["id_fornitore"],
            "id_operatore": operatore["id_operatore"],
            "data_ora": ts,
            "importo": importo,
            "tempo_erogazione_ore": None if np.isnan(tempo_ore) else round(float(tempo_ore), 1),
            "stato": stato,
        })
    return pd.DataFrame(righe)


# ---------------------------------------------------------------------------
# Introduzione controllata di imperfezioni (per testare la pulizia dell'ETL)
# ---------------------------------------------------------------------------

def sporca(rng, df, quota, colonne_testo=(), colonna_data=None, colonna_numero=None,
           duplica=True):
    """Restituisce una copia del dataframe con una piccola quota di difetti realistici."""
    if quota <= 0:
        return df
    df = df.copy().astype(object)
    n = len(df)
    k = max(1, int(n * quota))

    for col in colonne_testo:
        idx = rng.choice(n, size=k, replace=False)
        trasforma = [str.upper, str.lower, lambda s: f"  {s} "]
        df.loc[idx, col] = [trasforma[rng.integers(3)](str(v)) for v in df.loc[idx, col]]

    if colonna_data:
        idx = rng.choice(n, size=k, replace=False)
        df.loc[idx, colonna_data] = [pd.Timestamp(v).strftime("%d/%m/%Y %H:%M")
                                     if " " in str(v) or ":" in str(v)
                                     else pd.Timestamp(v).strftime("%d/%m/%Y")
                                     for v in df.loc[idx, colonna_data]]

    if colonna_numero:
        idx = rng.choice(n, size=k, replace=False)
        df.loc[idx, colonna_numero] = [str(v).replace(".", ",") for v in df.loc[idx, colonna_numero]]
        idx_vuoti = rng.choice(n, size=max(1, k // 3), replace=False)
        df.loc[idx_vuoti, colonna_numero] = None

    if duplica:
        dup = df.iloc[rng.choice(n, size=max(1, k // 2), replace=False)]
        df = pd.concat([df, dup]).sample(frac=1, random_state=int(rng.integers(1_000_000)))
        df = df.reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    radice = Path(__file__).resolve().parents[1]

    p = argparse.ArgumentParser(description="Genera i dati sintetici di TecnoSolution.")
    p.add_argument("--seed", type=int, default=42, help="seme casuale (riproducibilità)")
    p.add_argument("--clienti", type=int, default=450)
    p.add_argument("--fornitori", type=int, default=300)
    p.add_argument("--operatori", type=int, default=320)
    p.add_argument("--richieste", type=int, default=600)
    p.add_argument("--inizio", default="2025-07-01", help="inizio periodo (AAAA-MM-GG)")
    p.add_argument("--fine", default="2026-07-01", help="fine periodo, esclusa (AAAA-MM-GG)")
    p.add_argument("--annullate", type=float, default=0.08, help="quota di richieste annullate")
    p.add_argument("--ritardi", type=float, default=0.12, help="quota di richieste in ritardo")
    p.add_argument("--sporcizia", type=float, default=0.03,
                   help="quota di righe con imperfezioni da pulire nell'ETL (0 = dati puliti)")
    p.add_argument("--output", default=str(radice / "data" / "raw"))
    a = p.parse_args()

    for nome in ("clienti", "fornitori", "operatori", "richieste"):
        if not 300 <= getattr(a, nome) <= 600:
            print(f"Attenzione: la traccia chiede 300-600 record, {nome} = {getattr(a, nome)}")

    rng = np.random.default_rng(a.seed)
    inizio, fine = pd.Timestamp(a.inizio), pd.Timestamp(a.fine)

    clienti = genera_clienti(rng, a.clienti, inizio, fine - pd.Timedelta(days=1))
    fornitori = genera_fornitori(rng, a.fornitori)
    operatori = genera_operatori(rng, a.operatori)
    richieste = genera_richieste(rng, a.richieste, clienti, fornitori, operatori,
                                 inizio, fine, a.annullate, a.ritardi)

    # formati di esportazione "puliti"
    clienti["data_iscrizione"] = clienti["data_iscrizione"].dt.strftime("%Y-%m-%d")
    richieste["data_ora"] = pd.to_datetime(richieste["data_ora"]).dt.strftime("%Y-%m-%d %H:%M")

    # imperfezioni controllate
    clienti = sporca(rng, clienti, a.sporcizia, colonne_testo=["zona"],
                     colonna_data="data_iscrizione")
    fornitori = sporca(rng, fornitori, a.sporcizia, colonne_testo=["zona", "categoria_servizio"])
    operatori = sporca(rng, operatori, a.sporcizia, colonne_testo=["zona", "tipo_attivita"])
    richieste = sporca(rng, richieste, a.sporcizia, colonne_testo=["stato"],
                       colonna_data="data_ora", colonna_numero="importo")

    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    for nome, df in [("clienti", clienti), ("fornitori", fornitori),
                     ("operatori", operatori), ("richieste", richieste)]:
        df.to_csv(out / f"{nome}.csv", index=False, encoding="utf-8")
        print(f"{nome:<10} {len(df):>4} righe -> {out / (nome + '.csv')}")


if __name__ == "__main__":
    main()
