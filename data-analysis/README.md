# Carte interactive — Observations de cétacés aux Açores

Visualisation interactive des données MONICET avec un slider temporel par année.

## Prérequis

- Python 3.11+ (Python 3.12 testé)
- WSL Ubuntu 22.04 ou supérieur

## Installation des dépendances

### Étape 1 — Créer un environnement virtuel (recommandé sous WSL/Ubuntu)

Les systèmes Ubuntu récents bloquent l'installation globale de pip (PEP 668).
Utiliser un virtualenv :

```bash
# Depuis le dossier data-analysis/
python3 -m venv .venv
```

### Étape 2 — Activer l'environnement et installer les paquets

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

Ou en une commande sans activation :

```bash
.venv/bin/pip install -r requirements.txt
```

Paquets installés :
| Paquet    | Version min | Rôle                              |
|-----------|-------------|-----------------------------------|
| pandas    | 2.0         | Lecture et manipulation des CSV   |
| shapely   | 2.0         | Parsing des géométries WKT        |
| plotly    | 5.18        | Carte interactive + export HTML   |

## Utilisation

```bash
# Avec le venv activé
python cetaceans_map.py

# Ou directement
.venv/bin/python cetaceans_map.py
```

La carte est générée dans `data-analysis/cetaceans_map.html`.

## Ouvrir la carte

Depuis WSL, lancer directement dans le navigateur Windows :

```bash
explorer.exe cetaceans_map.html
```

Ou copier le chemin Linux vers un chemin Windows :
`\\wsl.localhost\Ubuntu\home\pierr\wdo-rd\data-analysis\cetaceans_map.html`

> **Note réseau** : la carte de fond (OpenStreetMap) nécessite une connexion internet.
> Pour un usage 100 % hors-ligne, modifier la ligne dans le script :
> ```python
> fig.write_html(..., include_plotlyjs=True, ...)  # embarque ~3 MB de JS
> ```

## Structure des fichiers

```
data-analysis/
├── cetaceans_map.py    # Script principal
├── cetaceans_map.html  # Carte générée (produit du script)
├── requirements.txt    # Dépendances Python
└── .venv/              # Environnement virtuel (local)
```

## Fonctionnalités de la carte

| Contrôle          | Description                                          |
|-------------------|------------------------------------------------------|
| Slider            | Filtre les observations par année (2009–2020)        |
| Points colorés    | Chaque couleur = une espèce (légende à gauche)       |
| Lignes oranges    | Trajets d'observation (encounters LINESTRING)        |
| Lignes grises     | Routes de croisière MONICET (MULTIPOINT)             |
| Survol souris     | Espèce, date, coordonnées et identifiant             |
| Molette / drag    | Zoom et déplacement de la carte                      |
