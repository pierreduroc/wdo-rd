"""
Carte interactive des observations de cétacés aux Açores
=========================================================
Données MONICET - Universidade dos Açores

Fonctionnalités :
  - Carte Mapbox centrée sur les Açores (open-street-map, sans token)
  - Points d'observation colorés par espèce
  - Trajets d'observation (LINESTRING) et routes de croisière (MULTIPOINT)
  - Slider interactif pour filtrer par année
  - Export HTML hors-ligne

Dépendances : pandas, shapely, plotly
"""

import sys
import warnings
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from shapely import wkt as shapely_wkt

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent.parent  # racine du projet
DATA_DIR = BASE_DIR / "wdo-datas"
OUTPUT_FILE = Path(__file__).parent / "cetaceans_map.html"

# Centre de la carte (île de São Miguel, Açores)
MAP_CENTER = {"lat": 37.75, "lon": -25.50}
MAP_ZOOM = 7

# Palette de couleurs pour les espèces (top 14 + "Autres")
SPECIES_PALETTE = [
    "#00B4D8", "#0077B6", "#90E0EF", "#48CAE4",
    "#F4A261", "#E76F51", "#2ECC71", "#27AE60",
    "#9B59B6", "#F1C40F", "#E74C3C", "#1ABC9C",
    "#3498DB", "#E67E22", "#95A5A6",
]

# ---------------------------------------------------------------------------
# 1. Chargement des données
# ---------------------------------------------------------------------------
print("Chargement des données…")

events = pd.read_csv(DATA_DIR / "event.txt", sep="\t", low_memory=False)
occurrences = pd.read_csv(DATA_DIR / "occurrence.txt", sep="\t", low_memory=False)

print(f"  → {len(events):,} événements chargés")
print(f"  → {len(occurrences):,} occurrences chargées")

# ---------------------------------------------------------------------------
# 2. Pré-traitement des événements
# ---------------------------------------------------------------------------

def parse_event_date(date_str):
    """
    Gère les formats :
      - '2009-01-06T10:55'          (instant)
      - '2009-01-06T09:15/2009-01-06T12:15'  (intervalle → prend le début)
    """
    if pd.isna(date_str):
        return pd.NaT
    start = str(date_str).split("/")[0]
    return pd.to_datetime(start, errors="coerce")


events["parsed_date"] = events["eventDate"].apply(parse_event_date)
events["year"] = events["parsed_date"].dt.year
events["month"] = events["parsed_date"].dt.month
events["date_label"] = events["parsed_date"].dt.strftime("%Y-%m-%d")

# Nettoyage des coordonnées
events = events.dropna(subset=["decimalLatitude", "decimalLongitude"])
events["decimalLatitude"] = pd.to_numeric(events["decimalLatitude"], errors="coerce")
events["decimalLongitude"] = pd.to_numeric(events["decimalLongitude"], errors="coerce")
events = events.dropna(subset=["decimalLatitude", "decimalLongitude", "year"])
events["year"] = events["year"].astype(int)

# ---------------------------------------------------------------------------
# 3. Association espèces ↔ événements
# ---------------------------------------------------------------------------
print("Association des espèces…")

# Regroupe toutes les espèces d'un échantillon en une seule chaîne
species_by_event = (
    occurrences.groupby("eventID")["scientificName"]
    .apply(lambda names: " / ".join(sorted(names.dropna().unique())))
    .reset_index()
    .rename(columns={"eventID": "id", "scientificName": "species_list"})
)

events = events.merge(species_by_event, on="id", how="left")
events["species_list"] = events["species_list"].fillna("Non identifié")

# Espèce principale (première mentionnée, pour la couleur)
events["primary_species"] = events["species_list"].apply(lambda s: s.split(" / ")[0])

# Palette de couleurs automatique pour les espèces les plus fréquentes
top_species = (
    events[events["type"] == "sample"]["primary_species"]
    .value_counts()
    .head(len(SPECIES_PALETTE) - 1)
    .index.tolist()
)
color_map = {sp: SPECIES_PALETTE[i] for i, sp in enumerate(top_species)}
color_map["Non identifié"] = "#95A5A6"


def get_color(species):
    return color_map.get(species, "#BDC3C7")


events["marker_color"] = events["primary_species"].apply(get_color)

# ---------------------------------------------------------------------------
# 4. Parsing des géométries WKT
# ---------------------------------------------------------------------------
print("Parsing des géométries WKT…")


def extract_line_coords(wkt_str):
    """
    Extrait les coordonnées d'une géométrie WKT sous forme de listes lat/lon.
    Retourne (lats, lons) prêtes pour go.Scattermapbox.
    Insère None comme séparateur de segments (technique standard Plotly).
    """
    lats, lons = [], []
    try:
        geom = shapely_wkt.loads(str(wkt_str))
    except Exception:
        return lats, lons

    if geom.geom_type == "LineString":
        for x, y in geom.coords:
            lons.append(x)
            lats.append(y)
        lons.append(None)
        lats.append(None)

    elif geom.geom_type == "MultiPoint":
        for pt in geom.geoms:
            lons.append(pt.x)
            lats.append(pt.y)
        # Relier les points dans l'ordre (trajectoire de croisière)
        lons.append(None)
        lats.append(None)

    return lats, lons


# Sépare les types d'événements
samples = events[events["type"] == "sample"].copy()   # observations d'espèces
cruises = events[events["type"] == "cruise"].copy()   # routes de croisière

print(f"  → {len(samples):,} échantillons / {len(cruises):,} croisières")

# ---------------------------------------------------------------------------
# 5. Construction de la figure Plotly
# ---------------------------------------------------------------------------
print("Construction de la carte…")

years_available = sorted(events["year"].dropna().unique().astype(int))
n_years = len(years_available)
print(f"  → Années disponibles : {years_available[0]} – {years_available[-1]}")

fig = go.Figure()

# Compteur de traces par année (nécessaire pour le slider)
traces_per_year = {}   # {year: [trace_index, ...]}
trace_index = 0

for year in years_available:
    year_indices = []
    visible = (year == years_available[0])  # seule la première année est visible

    s_year = samples[samples["year"] == year]

    # --- Trace A : Points d'observation (POINT) ---
    s_points = s_year[
        s_year["footprintWKT"].str.startswith("POINT", na=False)
    ]
    hover_text = (
        "<b>" + s_points["species_list"] + "</b><br>"
        + "Date : " + s_points["date_label"].fillna("?") + "<br>"
        + "Lat : " + s_points["decimalLatitude"].round(4).astype(str) + "<br>"
        + "Lon : " + s_points["decimalLongitude"].round(4).astype(str) + "<br>"
        + "ID : " + s_points["id"]
    )
    fig.add_trace(go.Scattermapbox(
        lat=s_points["decimalLatitude"].tolist(),
        lon=s_points["decimalLongitude"].tolist(),
        mode="markers",
        marker=dict(
            size=8,
            color=s_points["marker_color"].tolist(),
            opacity=0.85,
        ),
        text=hover_text.tolist(),
        hovertemplate="%{text}<extra></extra>",
        name=f"Observations {year}",
        visible=visible,
        legendgroup=f"year_{year}",
        showlegend=True,
    ))
    year_indices.append(trace_index)
    trace_index += 1

    # --- Trace B : Trajets d'observation (LINESTRING) ---
    s_lines = s_year[
        s_year["footprintWKT"].str.startswith("LINESTRING", na=False)
    ]
    all_lats, all_lons = [], []
    for _, row in s_lines.iterrows():
        lats, lons = extract_line_coords(row["footprintWKT"])
        all_lats.extend(lats)
        all_lons.extend(lons)

    if all_lats:
        fig.add_trace(go.Scattermapbox(
            lat=all_lats,
            lon=all_lons,
            mode="lines",
            line=dict(width=2, color="#F4A261"),
            name=f"Trajets obs. {year}",
            hoverinfo="skip",
            visible=visible,
            legendgroup=f"year_{year}",
            showlegend=False,
        ))
        year_indices.append(trace_index)
        trace_index += 1

    traces_per_year[year] = year_indices

total_traces = trace_index
print(f"  → {total_traces} traces créées")

# ---------------------------------------------------------------------------
# 6. Légende espèces (traces fantômes pour la légende)
# ---------------------------------------------------------------------------
# Ajoute des traces invisibles juste pour afficher la légende des espèces
legend_traces_start = trace_index
for sp, color in list(color_map.items())[:14]:
    short_name = sp.split()[-1] if sp != "Non identifié" else sp  # genre court
    fig.add_trace(go.Scattermapbox(
        lat=[None], lon=[None],
        mode="markers",
        marker=dict(size=10, color=color),
        name=sp,
        hoverinfo="skip",
        visible=True,
        showlegend=True,
    ))
    trace_index += 1

# ---------------------------------------------------------------------------
# 6b. Trace unique : Routes de croisière (toutes années, indépendante du slider)
# ---------------------------------------------------------------------------
# Toutes les croisières sont agrégées en UNE SEULE trace.
# Elle apparaît dans la légende — un clic suffit pour la masquer/afficher.
# Le slider ne modifie PAS sa visibilité (None dans le tableau des étapes
# → Plotly laisse la propriété inchangée).
cruise_trace_index = trace_index
all_lats_c, all_lons_c = [], []
for _, row in cruises.iterrows():
    wkt_str = str(row.get("footprintWKT", ""))
    if "MULTIPOINT" in wkt_str or "LINESTRING" in wkt_str:
        lats, lons = extract_line_coords(wkt_str)
        all_lats_c.extend(lats)
        all_lons_c.extend(lons)

fig.add_trace(go.Scattermapbox(
    lat=all_lats_c,
    lon=all_lons_c,
    mode="lines",
    line=dict(width=1.2, color="rgba(180,180,180,0.45)"),
    name="Routes de croisière",
    hoverinfo="skip",
    visible=True,
    showlegend=True,
    legendrank=1000,  # apparaît en bas de la légende
))
trace_index += 1
print(f"  → {len(all_lats_c):,} points de croisière (trace unique, togglable via légende)")

# ---------------------------------------------------------------------------
# 7. Slider années
# ---------------------------------------------------------------------------
slider_steps = []
for year in years_available:
    # Visibilité : True pour les traces de cette année, False pour les autres,
    #              True pour toutes les traces de légende (toujours visibles)
    visibility = []
    for y in years_available:
        n = len(traces_per_year[y])
        if y == year:
            visibility.extend([True] * n)
        else:
            visibility.extend([False] * n)
    # Traces de légende : toujours visibles
    n_legend = cruise_trace_index - legend_traces_start
    visibility.extend([True] * n_legend)
    # Trace de croisière globale : None = le slider ne touche pas sa visibilité,
    # l'utilisateur peut la toggler via la légende sans que le slider l'écrase.
    visibility.append(None)

    slider_steps.append(dict(
        method="update",
        args=[{"visible": visibility},
              {"title": f"Observations de cétacés aux Açores — {year}"}],
        label=str(year),
    ))

# ---------------------------------------------------------------------------
# 8. Mise en page
# ---------------------------------------------------------------------------
fig.update_layout(
    title=dict(
        text=f"Observations de cétacés aux Açores — {years_available[0]}",
        font=dict(size=18, color="#ECF0F1"),
        x=0.5,
    ),
    paper_bgcolor="#1A1A2E",
    plot_bgcolor="#1A1A2E",
    font=dict(color="#ECF0F1"),
    mapbox=dict(
        style="open-street-map",
        center=MAP_CENTER,
        zoom=MAP_ZOOM,
    ),
    legend=dict(
        bgcolor="rgba(26,26,46,0.85)",
        bordercolor="#4A4A6A",
        borderwidth=1,
        font=dict(size=11),
        title=dict(text="Espèces", font=dict(size=13)),
        x=0.01,
        y=0.99,
        xanchor="left",
        yanchor="top",
    ),
    sliders=[dict(
        active=0,
        currentvalue=dict(
            prefix="Année : ",
            visible=True,
            xanchor="center",
            font=dict(size=14, color="#ECF0F1"),
        ),
        pad={"b": 10, "t": 50},
        len=0.90,
        x=0.05,
        steps=slider_steps,
        bgcolor="#2D2D4E",
        activebgcolor="#00B4D8",
        bordercolor="#4A4A6A",
        font=dict(color="#ECF0F1"),
    )],
    margin=dict(l=0, r=0, t=60, b=80),
    height=750,
)

# ---------------------------------------------------------------------------
# 9. Export HTML
# ---------------------------------------------------------------------------
print(f"Export HTML → {OUTPUT_FILE}")
fig.write_html(
    str(OUTPUT_FILE),
    include_plotlyjs="cdn",   # ~3 KB au lieu d'inclure la lib complète (~3 MB)
    full_html=True,
    config={
        "scrollZoom": True,
        "displayModeBar": True,
        "modeBarButtonsToAdd": ["select2d", "lasso2d"],
    },
)
print(f"\nCarte générée avec succès : {OUTPUT_FILE.resolve()}")
print("Ouvrir dans un navigateur (connection internet requise pour la carte de fond).")
print("Pour un usage 100 % hors-ligne, remplacer include_plotlyjs='cdn' par include_plotlyjs=True.")
