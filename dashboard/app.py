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
BLU_AREA = "rgba(42,120,214,0.10)"
GRIGIO_GRIGLIA = "rgba(27,42,65,0.08)"
INCHIOSTRO = "#1b2a41"        # testo principale
INCHIOSTRO_2 = "#5b6b82"      # testo secondario (assi, etichette)
FONT = "Inter, 'Segoe UI', sans-serif"

CSS = """
<style>
header[data-testid="stHeader"] {background: transparent; height: 0;}
.block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1400px;}
h3 {font-size: 1.05rem !important; font-weight: 600 !important; margin-bottom: 0 !important;}
[data-testid="stVerticalBlockBorderWrapper"] {background: #ffffff;}

.ts-header {background: linear-gradient(120deg, #0d366b 0%, #184f95 60%, #256abf 100%);
            border-radius: 14px; padding: 22px 28px; margin-bottom: 18px; color: #fff;
            display: flex; align-items: center; justify-content: space-between; gap: 16px;
            flex-wrap: wrap;}
.ts-brand {display: flex; align-items: center; gap: 14px;}
.ts-logo {width: 44px; height: 44px; border-radius: 10px; background: rgba(255,255,255,0.14);
          display: flex; align-items: center; justify-content: center;}
.ts-title {font-size: 1.55rem; font-weight: 700; line-height: 1.2; letter-spacing: -0.01em;}
.ts-sub {font-size: 0.92rem; opacity: 0.82; margin-top: 2px;}
.ts-badge {background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.25);
           border-radius: 999px; padding: 6px 14px; font-size: 0.82rem; white-space: nowrap;}

.ts-kpi {background: #ffffff; border: 1px solid #e3e8f0; border-radius: 12px;
         padding: 14px 16px 12px; min-height: 112px; position: relative; overflow: hidden;}
.ts-kpi::before {content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
                 background: #2a78d6;}
.ts-kpi-label {font-size: 0.80rem; color: #5b6b82; font-weight: 500; white-space: nowrap;
               overflow: hidden; text-overflow: ellipsis;}
.ts-kpi-value {font-size: 1.75rem; font-weight: 700; color: #1b2a41; line-height: 1.25;
               margin-top: 4px; letter-spacing: -0.01em; font-variant-numeric: tabular-nums;}
.ts-kpi-note {font-size: 0.76rem; color: #7a889c; margin-top: 2px; white-space: nowrap;
              overflow: hidden; text-overflow: ellipsis;}

.ts-card-title {font-size: 1.02rem; font-weight: 600; color: #1b2a41; margin: 0;}
.ts-card-note {font-size: 0.84rem; color: #5b6b82; margin: 2px 0 4px 0;}
.ts-card-note b {color: #1b2a41; font-weight: 600;}
.ts-footer {font-size: 0.78rem; color: #7a889c; text-align: center; margin-top: 18px;}
</style>
"""

LOGO = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white"
stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0
1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6
6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>"""

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
        clienti = pd.read_sql_query("SELECT id_cliente, zona FROM dim_cliente", con)
    df["data"] = pd.to_datetime(df["data"])
    return df, clienti


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
        hoverlabel=dict(font_size=13, font_family=FONT, bgcolor="white",
                        bordercolor="#d5dce6", font_color=INCHIOSTRO),
        separators=",.",
        font=dict(family=FONT, color=INCHIOSTRO_2, size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#d5dce6", ticks="")
    fig.update_yaxes(gridcolor=GRIGIO_GRIGLIA, zeroline=False, ticks="")
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
        line=dict(color=BLU, width=2.5, shape="spline", smoothing=0.6),
        fill="tozeroy", fillcolor=BLU_AREA, cliponaxis=False,
        marker=dict(size=8, color=BLU, line=dict(width=2, color="white")),
        customdata=mensile[["etichetta", "incassi"]],
        hovertemplate="<b>%{customdata[0]}</b><br>Richieste: %{y}<br>"
                      "Incassi: %{customdata[1]:,.0f} €<extra></extra>",
    ))
    fig.update_xaxes(tickvals=mensile["mese"],
                     ticktext=[f"{MESI[d.month - 1]}<br>{d.year}" for d in mensile["mese"]],
                     range=[mensile["mese"].min() - pd.Timedelta(days=12),
                            mensile["mese"].max() + pd.Timedelta(days=12)])
    fig.update_yaxes(rangemode="tozero", title=None)
    return stile(fig, 330)


def grafico_barre_orizzontali(etichette, valori, testo_valori, hover, altezza=None):
    if altezza is None:  # spessore delle barre costante, indipendente dal numero di voci
        altezza = 60 + 44 * len(valori)
    fig = go.Figure(go.Bar(
        x=valori, y=etichette, orientation="h",
        marker=dict(color=BLU, cornerradius=4),
        text=testo_valori, textposition="outside", cliponaxis=False,
        textfont=dict(color=INCHIOSTRO, size=12),
        hovertemplate=hover + "<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)",
                     tickfont=dict(color=INCHIOSTRO, size=12.5), linecolor="rgba(0,0,0,0)")
    fig.update_xaxes(gridcolor=GRIGIO_GRIGLIA, showgrid=True, rangemode="tozero")
    fig = stile(fig, altezza)
    fig.update_layout(bargap=0.35, margin=dict(l=8, r=80, t=8, b=8))
    return fig


def grafico_top_fornitori(df, altezza=330):
    top = (df.groupby(["fornitore", "categoria_servizio"])
             .agg(incassi=("importo", "sum"), richieste=("id_richiesta", "count"))
             .reset_index()
             .sort_values("incassi", ascending=False)
             .head(5))
    fig = grafico_barre_orizzontali(
        top["fornitore"], top["incassi"],
        [euro(v) for v in top["incassi"]],
        "<b>%{y}</b><br>%{customdata[0]}<br>Incassi: %{x:,.2f} €<br>Richieste: %{customdata[1]}",
        altezza=altezza,
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
        colorbar=dict(title=dict(text="Richieste", side="right"), thickness=10,
                      outlinewidth=0),
        hovertemplate="<b>%{y} ore %{x}</b><br>Richieste: %{z}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(color=INCHIOSTRO))
    fig.update_xaxes(linecolor="rgba(0,0,0,0)")
    return stile(fig, 300)


# ---------------------------------------------------------------------------
# Pagina
# ---------------------------------------------------------------------------

def scheda_kpi(colonna, etichetta, valore, nota, aiuto):
    colonna.markdown(
        f'<div class="ts-kpi" title="{aiuto}"><div class="ts-kpi-label">{etichetta}</div>'
        f'<div class="ts-kpi-value">{valore}</div><div class="ts-kpi-note">{nota}</div></div>',
        unsafe_allow_html=True)


def titolo_riquadro(titolo, nota):
    st.markdown(f'<p class="ts-card-title">{titolo}</p><p class="ts-card-note">{nota}</p>',
                unsafe_allow_html=True)


def etichetta_mese(anno_mese):
    anno, mese = anno_mese.split("-")
    return f"{MESI[int(mese) - 1]} {anno}"


def main():
    st.set_page_config(page_title="TecnoSolution – Dashboard", page_icon="🛠️", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)

    if not FILE_DB.exists():
        st.error("Data warehouse non trovato. Esegui prima:  `python src/genera_dati.py`  e  "
                 "`python src/etl.py`")
        st.stop()

    dati, clienti = carica_dati()
    data_min, data_max = dati["data"].min().date(), dati["data"].max().date()

    st.markdown(
        f'''<div class="ts-header"><div class="ts-brand"><div class="ts-logo">{LOGO}</div><div>
        <div class="ts-title">TecnoSolution · Analisi delle richieste</div>
        <div class="ts-sub">Assistenza tecnica IT on-demand nei 9 capoluoghi siciliani</div></div></div>
        <div class="ts-badge">Dati sintetici · {MESI[data_min.month - 1]} {data_min.year} –
        {MESI[data_max.month - 1]} {data_max.year}</div></div>''',
        unsafe_allow_html=True)

    # --- Filtri in una riga sopra i grafici --------------------------------
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.2, 1, 1])
        periodo = c1.date_input("Periodo", value=(data_min, data_max),
                                min_value=data_min, max_value=data_max, format="DD/MM/YYYY")
        zone = c2.multiselect("Zona", sorted(dati["zona"].unique()), placeholder="Tutte le zone")
        categorie = c3.multiselect("Categoria di servizio",
                                   sorted(dati["categoria_servizio"].unique()),
                                   placeholder="Tutte le categorie")

    inizio, fine = (periodo if isinstance(periodo, (list, tuple)) and len(periodo) == 2
                    else (data_min, data_max))
    df = dati[(dati["data"] >= pd.Timestamp(inizio)) & (dati["data"] <= pd.Timestamp(fine))]
    if zone:
        df = df[df["zona"].isin(zone)]
        clienti = clienti[clienti["zona"].isin(zone)]
    if categorie:
        df = df[df["categoria_servizio"].isin(categorie)]

    if df.empty:
        st.warning("Nessuna richiesta corrisponde ai filtri selezionati.")
        st.stop()

    # --- Indicatori principali ---------------------------------------------
    k = calcola_kpi(df)
    erogate = df[df["flag_annullata"] == 0]
    scontrino = erogate["importo"].mean() if len(erogate) else 0
    m = st.columns(6)
    scheda_kpi(m[0], "Richieste totali", num(k["richieste"]),
               f"di cui {num(k['perc_annullate'], 1)}% annullate",
               "Tutte le richieste del periodo, comprese le annullate")
    scheda_kpi(m[1], "Incassi", euro(k["incassi"]),
               f"{euro(scontrino)} medi a intervento",
               "Somma degli importi delle richieste non annullate")
    scheda_kpi(m[2], "Tempo medio", f"{num(k['tempo_medio'], 1)} h",
               "di erogazione · SLA 48 h",
               "Ore medie tra richiesta e completamento (escluse le annullate)")
    scheda_kpi(m[3], "Clienti attivi", num(k["clienti_attivi"]),
               f"su {num(len(clienti))} iscritti",
               "Clienti con almeno una richiesta erogata nel periodo")
    scheda_kpi(m[4], "Clienti che tornano", f"{num(k['perc_tornano'], 1)}%",
               "con almeno 2 interventi",
               "Quota dei clienti attivi con almeno due richieste erogate")
    scheda_kpi(m[5], "Interventi in ritardo", f"{num(k['perc_ritardi'], 1)}%",
               "completati oltre le 48 h",
               "Quota delle richieste erogate completate oltre 48 ore")

    st.write("")

    # --- Grafici -------------------------------------------------------------
    mensile = df.groupby("anno_mese").size()
    top = df.groupby("fornitore")["importo"].sum().sort_values(ascending=False)
    per_zona = df["zona"].value_counts()
    per_cat = df["categoria_servizio"].value_counts()
    fascia = df.groupby(["giorno_settimana", "ora"]).size().idxmax()

    sx, dx = st.columns([1.4, 1])
    with sx, st.container(border=True):
        titolo_riquadro("Andamento delle richieste nel tempo",
                        f"Mese con più richieste: <b>{etichetta_mese(mensile.idxmax())}</b> "
                        f"({mensile.max()} richieste)")
        st.plotly_chart(grafico_andamento(df, inizio, fine), width="stretch")
    with dx, st.container(border=True):
        titolo_riquadro("Top 5 fornitori per incassi",
                        f"In testa <b>{top.index[0]}</b> con {euro(top.iloc[0])}")
        st.plotly_chart(grafico_top_fornitori(df), width="stretch")

    sx, dx = st.columns(2)
    with sx, st.container(border=True):
        quota = 100 * per_zona.head(2).sum() / per_zona.sum()
        titolo_riquadro("Richieste per zona",
                        f"<b>{per_zona.index[0]}</b> e <b>{per_zona.index[1]}</b> insieme "
                        f"raccolgono il {num(quota)}% delle richieste" if len(per_zona) > 1
                        else f"Zona selezionata: <b>{per_zona.index[0]}</b>")
        st.plotly_chart(grafico_conteggio(df, "zona"), width="stretch")
    with dx, st.container(border=True):
        titolo_riquadro("Richieste per categoria di servizio",
                        f"Categoria più richiesta: <b>{per_cat.index[0]}</b>")
        st.plotly_chart(grafico_conteggio(df, "categoria_servizio"), width="stretch")

    with st.container(border=True):
        titolo_riquadro("Quando arrivano le richieste (giorno e ora)",
                        f"Fascia più intensa: <b>{GIORNI[fascia[0] - 1]} ore {fascia[1]}:00</b>")
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

    st.markdown('<div class="ts-footer">Project Work · Informatica per le Aziende Digitali (L-31) · '
                'dati sintetici generati con src/genera_dati.py (seed 42)</div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
