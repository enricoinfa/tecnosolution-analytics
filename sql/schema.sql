-- =====================================================================
-- TecnoSolution – Data warehouse con schema a stella (SQLite)
--
-- Tabella dei fatti:  fatto_richieste   (una riga per richiesta di servizio)
-- Dimensioni:         dim_cliente, dim_fornitore, dim_operatore, dim_tempo
--
-- Le dimensioni usano chiavi surrogate (sk_*) distinte dai codici di origine
-- (id_*): questo isola il warehouse dai sistemi sorgente e permette in futuro
-- di storicizzare le modifiche (Slowly Changing Dimensions).
-- =====================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fatto_richieste;
DROP TABLE IF EXISTS dim_cliente;
DROP TABLE IF EXISTS dim_fornitore;
DROP TABLE IF EXISTS dim_operatore;
DROP TABLE IF EXISTS dim_tempo;

-- ---------------------------------------------------------------------
-- Dimensione Cliente
-- ---------------------------------------------------------------------
CREATE TABLE dim_cliente (
    sk_cliente        INTEGER PRIMARY KEY,
    id_cliente        TEXT    NOT NULL UNIQUE,
    zona              TEXT    NOT NULL,
    data_iscrizione   TEXT    NOT NULL,          -- AAAA-MM-GG
    anno_mese_iscrizione TEXT NOT NULL           -- AAAA-MM, utile per analisi per coorte
);

-- ---------------------------------------------------------------------
-- Dimensione Fornitore (partner che eroga la categoria di servizio)
-- ---------------------------------------------------------------------
CREATE TABLE dim_fornitore (
    sk_fornitore        INTEGER PRIMARY KEY,
    id_fornitore        TEXT    NOT NULL UNIQUE,
    nome                TEXT    NOT NULL,
    categoria_servizio  TEXT    NOT NULL,
    zona                TEXT    NOT NULL
);

-- ---------------------------------------------------------------------
-- Dimensione Operatore (tecnico che svolge l'intervento)
-- ---------------------------------------------------------------------
CREATE TABLE dim_operatore (
    sk_operatore    INTEGER PRIMARY KEY,
    id_operatore    TEXT    NOT NULL UNIQUE,
    zona            TEXT    NOT NULL,
    tipo_attivita   TEXT    NOT NULL
);

-- ---------------------------------------------------------------------
-- Dimensione Tempo (granularità: giorno)
-- La chiave è la data in formato numerico AAAAMMGG.
-- ---------------------------------------------------------------------
CREATE TABLE dim_tempo (
    id_tempo          INTEGER PRIMARY KEY,       -- es. 20260115
    data              TEXT    NOT NULL UNIQUE,   -- AAAA-MM-GG
    anno              INTEGER NOT NULL,
    trimestre         INTEGER NOT NULL,
    mese              INTEGER NOT NULL,
    nome_mese         TEXT    NOT NULL,
    anno_mese         TEXT    NOT NULL,          -- AAAA-MM
    settimana_iso     INTEGER NOT NULL,
    giorno_settimana  INTEGER NOT NULL,          -- 1 = lunedì ... 7 = domenica
    nome_giorno       TEXT    NOT NULL,
    weekend           INTEGER NOT NULL CHECK (weekend IN (0, 1))
);

-- ---------------------------------------------------------------------
-- Tabella dei fatti: Richieste
-- Misure: importo, tempo_erogazione_ore, flag per conteggi rapidi
-- ---------------------------------------------------------------------
CREATE TABLE fatto_richieste (
    id_richiesta          TEXT    PRIMARY KEY,   -- dimensione degenere
    sk_cliente            INTEGER NOT NULL REFERENCES dim_cliente(sk_cliente),
    sk_fornitore          INTEGER NOT NULL REFERENCES dim_fornitore(sk_fornitore),
    sk_operatore          INTEGER NOT NULL REFERENCES dim_operatore(sk_operatore),
    id_tempo              INTEGER NOT NULL REFERENCES dim_tempo(id_tempo),
    ora                   INTEGER NOT NULL CHECK (ora BETWEEN 0 AND 23),
    stato                 TEXT    NOT NULL CHECK (stato IN ('Completata', 'In ritardo', 'Annullata')),
    importo               REAL    NOT NULL CHECK (importo >= 0),
    importo_stimato       INTEGER NOT NULL DEFAULT 0 CHECK (importo_stimato IN (0, 1)),
    tempo_erogazione_ore  REAL,                  -- NULL per le richieste annullate
    flag_annullata        INTEGER NOT NULL CHECK (flag_annullata IN (0, 1)),
    flag_ritardo          INTEGER NOT NULL CHECK (flag_ritardo IN (0, 1))
);

-- Indici sulle chiavi esterne per velocizzare join e filtri della dashboard
CREATE INDEX idx_fatto_cliente   ON fatto_richieste(sk_cliente);
CREATE INDEX idx_fatto_fornitore ON fatto_richieste(sk_fornitore);
CREATE INDEX idx_fatto_operatore ON fatto_richieste(sk_operatore);
CREATE INDEX idx_fatto_tempo     ON fatto_richieste(id_tempo);
