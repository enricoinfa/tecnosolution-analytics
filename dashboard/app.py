"""
Dashboard interattiva di TecnoSolution (Streamlit).

Legge il data warehouse SQLite (schema a stella), applica i filtri scelti
dall'utente (periodo, zona, categoria di servizio) e mostra:
  - gli indicatori principali (richieste, incassi, tempo medio, clienti attivi,
    clienti che tornano, ritardi)
  - l'andamento delle richieste nel tempo
  - la classifica dei primi 5 fornitori per incassi
  - la distribuzione delle richieste per zona e per categoria di servizio
  - la distribuzione per giorno della settimana e fascia oraria

Avvio (dalla cartella del progetto):
    streamlit run dashboard/app.py
"""

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RADICE = Path(__file__).resolve().parents[1]
FILE_DB = RADICE / "data" / "warehouse" / "tecnosolution.db"

# Colori (palette validata per daltonismo): una sola tinta per i grafici a serie singola,
# rampa sequenziale dello stesso blu per la mappa di calore
BLU = "#2a78d6"
RAMPA_BLU = ["#f4f8fd", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
GRIGIO_GRIGLIA = "rgba(128,128,128,0.18)"

GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]

# Vista denormalizzata: il fatto unito alle quattro dimensioni della stella
QUERY_BASE = """
SELECT
    f.id_richiesta,
    t.data,
    t.anno_mese,
    t.giorno_settimana,
    f.ora,
    c.id_cliente,
    c.zona,
    fo.nome            AS fornitore,
    fo.categoria_servizio,
    o.tipo_attivita,
    f.stato,
    f.importo,
    f.tempo_erogazione_ore,
    f.flag_annullata,
    f.flag_ritardo
FROM fatto_richieste f
JOIN dim_tempo     t  ON t.id_tempo      = f.id_tempo
JOIN dim_cliente   c  ON c.sk_cliente    = f.sk_cliente
JOIN dim_fornitore fo ON fo.sk_fornitore = f.sk_fornitore
JOIN dim_operatore o  ON o.sk_operatore  = f.sk_operatore
"""


# ---------------------------------------------------------------------------
# Formattazione all'italiana
# ---------------------------------------------------------------------------

def num(x, decimali=0):
    testo = f"{x:,.{decimali}f}"
    return testo.replace(",", "X").replace(".", ",").replace("X", ".")


def euro(x, decimali=0):
    return f"{num(x, decimali)} €"


# ---------------------------------------------------------------------------
# Dati
# ---------------------------------------------------------------------------

@st.cache_data
def carica_dati():
    with sqlite3.connect(FILE_DB) as con:
        df = pd.read_sql_query(QUERY_BASE, con)
    df["data"] = pd.to_datetime(df["data"])
    return df


def calcola_kpi(df):
    erogate = df[df["flag_annullata"] == 0]
    per_cliente = erogate.groupby("id_cliente").size()
    return {
        "richieste": len(df),
        "incassi": df["importo"].sum(),
        "tempo_medio": erogate["tempo_erogazione_ore"].mean(),
        "clienti_attivi": erogate["id_cliente"].nunique(),
        "perc_tornano": 100 * (per_cliente >= 2).mean() if len(per_cliente) else float("nan"),
        "perc_ritardi": 100 * erogate["flag_ritardo"].mean() if len(erogate) else float("nan"),
        "perc_annullate": 100 * df["flag_annullata"].mean() if len(df) else float("nan"),
    }


# ---------------------------------------------------------------------------
# Grafici (Plotly) – segni sottili, griglia leggera, tooltip in italiano
# ---------------------------------------------------------------------------

def stile(fig, altezza=320):
    fig.update_layout(
        height=altezza,
        margin=dict(l=8, r=8, t=8, b=8),
        showlegend=False,
        hoverlabel=dict(font_size=13),
        separators=",.",
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor=GRIGIO_GRIGLIA, zeroline=False)
    return fig


def grafico_andamento(df, inizio, fine):
    # tutti i mesi del periodo selezionato, anche quelli senza richieste (valore 0)
    tutti = pd.period_range(pd.Timestamp(inizio), pd.Timestamp(fine), freq="M").strftime("%Y-%m")
    mensile = (df.groupby("anno_mese")
                 .agg(richieste=("id_richiesta", "count"), incassi=("importo", "sum"))
                 .reindex(tutti, fill_value=0)
                 .rename_axis("anno_mese")
                 .reset_index())
    mensile["mese"] = pd.to_datetime(mensile["anno_mese"] + "-01")
    mensile["etichetta"] = [f"{MESI[d.month - 1]} {d.year}" for d in mensile["mese"]]
    fig = go.Figure(go.Scatter(
        x=mensile["mese"], y=mensile["richieste"],
        mode="lines+markers",
        line=dict(color=BLU, width=2),
        marker=dict(size=8, color=BLU, line=dict(width=2, color="white")),
        customdata=mensile[["etichetta", "incassi"]],
        hovertemplate="<b>%{customdata[0]}</b><br>Richieste: %{y}<br>"
                      "Incassi: %{customdata[1]:,.0f} €<extra></extra>",
    ))
    fig.update_xaxes(tickvals=mensile["mese"],
                     ticktext=[f"{MESI[d.month - 1]}<br>{d.year}" for d in mensile["mese"]])
    fig.update_yaxes(rangemode="tozero", title=None)
    return stile(fig)


def grafico_barre_orizzontali(etichette, valori, testo_valori, hover, altezza=None):
    if altezza is None:  # spessore delle barre costante, indipendente dal numero di voci
        altezza = 60 + 44 * len(valori)
    fig = go.Figure(go.Bar(
        x=valori, y=etichette, orientation="h",
        marker=dict(color=BLU, cornerradius=4),
        text=testo_valori, textposition="outside", cliponaxis=False,
        hovertemplate=hover + "<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(gridcolor=GRIGIO_GRIGLIA, showgrid=True, rangemode="tozero")
    fig = stile(fig, altezza)
    fig.update_layout(bargap=0.35, margin=dict(l=8, r=60, t=8, b=8))
    return fig


def grafico_top_fornitori(df):
    top = (df.groupby(["fornitore", "categoria_servizio"])
             .agg(incassi=("importo", "sum"), richieste=("id_richiesta", "count"))
             .reset_index()
             .sort_values("incassi", ascending=False)
             .head(5))
    fig = grafico_barre_orizzontali(
        top["fornitore"], top["incassi"],
        [euro(v) for v in top["incassi"]],
        "<b>%{y}</b><br>%{customdata[0]}<br>Incassi: %{x:,.2f} €<br>Richieste: %{customdata[1]}",
    )
    fig.update_traces(customdata=top[["categoria_servizio", "richieste"]])
    return fig


def grafico_conteggio(df, colonna):
    conteggi = df.groupby(colonna).size().sort_values(ascending=False)
    totale = conteggi.sum()
    return grafico_barre_orizzontali(
        conteggi.index, conteggi.values,
        [f"{v} ({num(100 * v / totale, 0)}%)" for v in conteggi.values],
        "<b>%{y}</b><br>Richieste: %{x}",
    )


def grafico_giorno_ora(df):
    tabella = (df.groupby(["giorno_settimana", "ora"]).size()
                 .unstack(fill_value=0)
                 .reindex(index=range(1, 8), columns=range(7, 23), fill_value=0))
    fig = go.Figure(go.Heatmap(
        z=tabella.values,
        x=[f"{h}:00" for h in tabella.columns],
        y=GIORNI,
        colorscale=[[i / (len(RAMPA_BLU) - 1), c] for i, c in enumerate(RAMPA_BLU)],
        xgap=2, ygap=2,
        colorbar=dict(title=dict(text="Richieste", side="right"), thickness=12),
        hovertemplate="<b>%{y} ore %{x}</b><br>Richieste: %{z}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return stile(fig, 300)


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="TecnoSolution – Dashboard", page_icon="🛠️", layout="wide")

    if not FILE_DB.exists():
        st.error("Data warehouse non trovato. Esegui prima:  `python src/genera_dati.py`  e  "
                 "`python src/etl.py`")
        st.stop()

    dati = carica_dati()

    st.title("TecnoSolution – Analisi delle richieste")
    st.caption("Assistenza tecnica IT on-demand nei capoluoghi siciliani · dati sintetici")

    # --- Filtri in una riga sopra i grafici --------------------------------
    c1, c2, c3 = st.columns([1.2, 1, 1])
    data_min, data_max = dati["data"].min().date(), dati["data"].max().date()
    periodo = c1.date_input("Periodo", value=(data_min, data_max),
                            min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
    zone = c2.multiselect("Zona", sorted(dati["zona"].unique()), placeholder="Tutte le zone")
    categorie = c3.multiselect("Categoria di servizio", sorted(dati["categoria_servizio"].unique()),
                               placeholder="Tutte le categorie")

    inizio, fine = (periodo if isinstance(periodo, (list, tuple)) and len(periodo) == 2
                    else (data_min, data_max))
    df = dati[(dati["data"] >= pd.Timestamp(inizio)) & (dati["data"] <= pd.Timestamp(fine))]
    if zone:
        df = df[df["zona"].isin(zone)]
    if categorie:
        df = df[df["categoria_servizio"].isin(categorie)]

    if df.empty:
        st.warning("Nessuna richiesta corrisponde ai filtri selezionati.")
        st.stop()

    # --- Indicatori principali ---------------------------------------------
    k = calcola_kpi(df)
    m = st.columns(6)
    m[0].metric("Richieste totali", num(k["richieste"]),
                help="Tutte le richieste del periodo, comprese le annullate "
                     f"({num(k['perc_annullate'], 1)}%)")
    m[1].metric("Incassi", euro(k["incassi"]), help="Somma degli importi delle richieste non annullate")
    m[2].metric("Tempo medio di erogazione", f"{num(k['tempo_medio'], 1)} h",
                help="Ore medie tra richiesta e completamento (escluse le annullate)")
    m[3].metric("Clienti attivi", num(k["clienti_attivi"]),
                help="Clienti con almeno una richiesta erogata nel periodo")
    m[4].metric("Clienti che tornano", f"{num(k['perc_tornano'], 1)}%",
                help="Quota dei clienti attivi con almeno due richieste erogate")
    m[5].metric("Interventi in ritardo", f"{num(k['perc_ritardi'], 1)}%",
                help="Quota delle richieste erogate completate oltre 48 ore")

    st.divider()

    # --- Grafici -------------------------------------------------------------
    sx, dx = st.columns([1.4, 1])
    with sx:
        st.subheader("Andamento delle richieste nel tempo")
        st.plotly_chart(grafico_andamento(df, inizio, fine), width="stretch")
    with dx:
        st.subheader("Top 5 fornitori per incassi")
        st.plotly_chart(grafico_top_fornitori(df), width="stretch")

    sx, dx = st.columns(2)
    with sx:
        st.subheader("Richieste per zona")
        st.plotly_chart(grafico_conteggio(df, "zona"), width="stretch")
    with dx:
        st.subheader("Richieste per categoria di servizio")
        st.plotly_chart(grafico_conteggio(df, "categoria_servizio"), width="stretch")

    st.subheader("Quando arrivano le richieste (giorno e ora)")
    st.plotly_chart(grafico_giorno_ora(df), width="stretch")

    # --- Vista tabellare (accessibilità e verifica) --------------------------
    with st.expander("Dati in tabella"):
        riepilogo = (df.groupby(["zona", "categoria_servizio"])
                       .agg(richieste=("id_richiesta", "count"),
                            incassi=("importo", "sum"),
                            tempo_medio_ore=("tempo_erogazione_ore", "mean"))
                       .round(1).reset_index())
        st.dataframe(riepilogo, width="stretch", hide_index=True)
        st.download_button("Scarica le richieste filtrate (CSV)",
                           df.to_csv(index=False).encode("utf-8"),
                           file_name="richieste_filtrate.csv", mime="text/csv")


if __name__ == "__main__":
    main()
