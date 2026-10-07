-- =====================================================================
-- TecnoSolution – Interrogazioni SQL per gli indicatori (KPI)
--
-- Ogni query è preceduta da una riga "-- name: <nome>" così che
-- src/kpi.py e la dashboard possano richiamarla per nome.
--
-- Convenzioni:
--   * le richieste annullate contano nel numero di richieste ma non negli
--     incassi né nel tempo medio di erogazione;
--   * la zona di riferimento è quella del cliente (dove avviene l'intervento).
-- =====================================================================

-- name: kpi_principali
SELECT
    COUNT(*)                                                    AS richieste_totali,
    SUM(CASE WHEN f.flag_annullata = 0 THEN 1 ELSE 0 END)       AS richieste_erogate,
    ROUND(SUM(f.importo), 2)                                    AS incassi_totali,
    ROUND(AVG(CASE WHEN f.flag_annullata = 0
                   THEN f.tempo_erogazione_ore END), 1)         AS tempo_medio_ore,
    COUNT(DISTINCT CASE WHEN f.flag_annullata = 0
                        THEN f.sk_cliente END)                  AS clienti_attivi,
    ROUND(100.0 * SUM(f.flag_annullata) / COUNT(*), 1)          AS perc_annullate,
    ROUND(100.0 * SUM(f.flag_ritardo)
          / NULLIF(SUM(1 - f.flag_annullata), 0), 1)            AS perc_ritardi
FROM fatto_richieste f;

-- name: clienti_che_tornano
-- Quota di clienti con almeno una richiesta erogata che ne hanno fatte almeno due
WITH per_cliente AS (
    SELECT sk_cliente, COUNT(*) AS n
    FROM fatto_richieste
    WHERE flag_annullata = 0
    GROUP BY sk_cliente
)
SELECT
    COUNT(*)                                            AS clienti_con_richieste,
    SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END)             AS clienti_ricorrenti,
    ROUND(100.0 * SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END) / COUNT(*), 1)
                                                        AS perc_clienti_che_tornano
FROM per_cliente;

-- name: andamento_mensile
SELECT
    t.anno_mese,
    COUNT(*)                     AS richieste,
    ROUND(SUM(f.importo), 2)     AS incassi
FROM fatto_richieste f
JOIN dim_tempo t ON t.id_tempo = f.id_tempo
GROUP BY t.anno_mese
ORDER BY t.anno_mese;

-- name: top5_fornitori_incassi
SELECT
    fo.nome,
    fo.categoria_servizio,
    fo.zona,
    COUNT(*)                   AS richieste,
    ROUND(SUM(f.importo), 2)   AS incassi
FROM fatto_richieste f
JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
GROUP BY fo.sk_fornitore
ORDER BY incassi DESC
LIMIT 5;

-- name: richieste_per_zona
SELECT
    c.zona,
    COUNT(*)                   AS richieste,
    ROUND(SUM(f.importo), 2)   AS incassi
FROM fatto_richieste f
JOIN dim_cliente c ON c.sk_cliente = f.sk_cliente
GROUP BY c.zona
ORDER BY richieste DESC;

-- name: richieste_per_categoria
SELECT
    fo.categoria_servizio,
    COUNT(*)                                            AS richieste,
    ROUND(SUM(f.importo), 2)                            AS incassi,
    ROUND(AVG(CASE WHEN f.flag_annullata = 0
                   THEN f.tempo_erogazione_ore END), 1) AS tempo_medio_ore
FROM fatto_richieste f
JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
GROUP BY fo.categoria_servizio
ORDER BY richieste DESC;

-- name: richieste_per_giorno_e_ora
SELECT
    t.giorno_settimana,
    t.nome_giorno,
    f.ora,
    COUNT(*) AS richieste
FROM fatto_richieste f
JOIN dim_tempo t ON t.id_tempo = f.id_tempo
GROUP BY t.giorno_settimana, t.nome_giorno, f.ora
ORDER BY t.giorno_settimana, f.ora;
