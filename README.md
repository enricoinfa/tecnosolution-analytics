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

I comandi per generare i dati, eseguire l'ETL e avviare la dashboard verranno aggiunti man mano che i componenti sono completati.
