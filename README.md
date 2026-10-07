# TecnoSolution Analytics

Prototipo di analisi dati per **TecnoSolution**, una startup (inventata) di assistenza tecnica IT on-demand attiva nei capoluoghi siciliani.

Project Work di laurea – Informatica per le Aziende Digitali (L-31), Università Telematica Pegaso.
Tema 1 "La digitalizzazione dell'impresa", traccia 21.

> Tutti i dati sono sintetici, generati per l'occasione, senza alcuna informazione personale.

## Cosa contiene

| Componente | File | Descrizione |
|---|---|---|
| Generatore dati | `src/genera_dati.py` | crea clienti, fornitori, operatori e richieste in CSV |
| ETL | `src/etl.py` | legge i CSV, li pulisce e li carica nel data warehouse SQLite |
| Data warehouse | `data/warehouse/tecnosolution.db` | schema a stella: fatto Richieste + dimensioni Cliente, Fornitore, Operatore, Tempo |
| Query KPI | `sql/` | interrogazioni SQL per gli indicatori principali |
| Dashboard | `dashboard/app.py` | dashboard interattiva Streamlit |

## Struttura delle cartelle

```
tecnosolution-analytics/
├── data/
│   ├── raw/          # CSV generati
│   └── warehouse/    # database SQLite
├── src/              # generatore dati ed ETL
├── sql/              # schema e query KPI
├── dashboard/        # app Streamlit
└── docs/img/         # screenshot per il report
```

## Come riprodurre il lavoro

Requisiti: Python 3.12.

```
python -m venv .venv
.venv\Scripts\activate          # su macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 1. Generare i dati sintetici

```
python src/genera_dati.py
```

Crea `clienti.csv`, `fornitori.csv`, `operatori.csv` e `richieste.csv` in `data/raw/`.
Parametri principali (tutti facoltativi):

| Parametro | Default | Significato |
|---|---|---|
| `--seed` | 42 | seme casuale: stesso seme = stessi dati |
| `--clienti` / `--fornitori` / `--operatori` / `--richieste` | 450 / 300 / 320 / 600 | numero di record (la traccia chiede 300–600) |
| `--inizio` / `--fine` | 2025-07-01 / 2026-07-01 | periodo coperto dalle richieste |
| `--annullate` / `--ritardi` | 0.08 / 0.12 | quota di richieste annullate e in ritardo (oltre 48 ore) |
| `--sporcizia` | 0.03 | quota di righe con imperfezioni da correggere nell'ETL (0 = dati già puliti) |

Le imperfezioni introdotte di proposito (maiuscole e spazi incoerenti, date in formato italiano, virgola decimale, valori mancanti, righe duplicate) servono a verificare la fase di pulizia dell'ETL.

I comandi per l'ETL e la dashboard verranno aggiunti man mano che i componenti sono completati.
