# Accessibilité des établissements recevant du public

Carte interactive des établissements recevant du public (ERP) recensés dans [Acceslibre](https://acceslibre.beta.gouv.fr/), colorés selon l'accessibilité déclarée de leur entrée. Un clic sur un établissement ouvre sa fiche d'accessibilité complète : stationnement, chemin extérieur, entrée, accueil, sanitaires, hébergement, labels, avec des liens vers Acceslibre et vers le bâtiment dans le [Référentiel national des bâtiments](https://rnb.beta.gouv.fr/).

**Voir la carte : https://nicolasberthelot.github.io/accessibilite-erp-acceslibre/**

## Contenu de la carte

- Environ 635 000 établissements géolocalisés, répartis en quatre catégories selon leur entrée :
  - de plain-pied ;
  - accessible avec aménagement (rampe, ascenseur ou entrée PMR dédiée) ;
  - marches sans aménagement déclaré ;
  - non renseignée.
- Filtres par catégorie et par type d'activité (mairie, pharmacie…), avec les effectifs et les parts recalculés.
- Recherche d'une commune ou d'une adresse (service d'autocomplétion de la Géoplateforme).
- Fiche par établissement reprenant les 84 critères d'accessibilité du jeu de données.

Les informations sont celles déclarées par les contributeurs d'Acceslibre, sans vérification sur place.

## Données et services

- **Données** : [Accessibilité des établissements recevant du public (ERP) pour les personnes en situation de handicap](https://www.data.gouv.fr/datasets/accessibilite-des-etablissements-recevant-du-public-erp-pour-les-personnes-en-situation-de-handicap), Acceslibre, sur data.gouv.fr — Licence Ouverte 2.0. Export Parquet du 29 octobre 2026.
- **Fond de carte** : Plan IGN, Géoplateforme de l'IGN.
- **Bibliothèques** intégrées à la page : [MapLibre GL JS](https://maplibre.org/) (licence BSD-3-Clause) et [deck.gl](https://deck.gl/) (licence MIT).

## Organisation du dépôt

- `index.html` : la page (interface, filtres, fiches).
- `lib/` : MapLibre GL JS et deck.gl, servis avec le site.
- `donnees/erp.json.gz` : établissements (positions, noms, adresses, liens), compressé.
- `donnees/criteres.bin.gz` : critères d'accessibilité codés, compressé.
- `scripts/` : script de génération et modèle de page.

Les données sont chargées et décompressées par le navigateur au démarrage (environ 26 Mo). Seuls le fond de carte et la recherche d'adresse font appel à des services extérieurs. Pour consulter la carte en local, il faut passer par un serveur web, par exemple `python3 -m http.server`, car les navigateurs bloquent le chargement des fichiers depuis `file://`.

## Mettre à jour les données

Le script `scripts/build.py` produit le site (page, bibliothèques et données) à partir de l'export Parquet du jeu de données. La date passée en dernier argument est celle de l'export, affichée sur la carte.

```bash
pip install duckdb
# Export Parquet de la ressource complète (avec l'URL des fiches Acceslibre)
curl -o erp.parquet https://hydra.s3.rbx.io.cloud.ovh.net/parquet/93ae96a7-1db7-4cb4-a9f1-6d778370b640.parquet
# Bibliothèques JavaScript intégrées à la page
npm pack maplibre-gl@4 deck.gl@9 && mkdir -p vendor/maplibre vendor/deck
tar xzf maplibre-gl-*.tgz -C vendor/maplibre && tar xzf deck.gl-*.tgz -C vendor/deck
# Génération
python3 scripts/build.py erp.parquet . scripts/template.html \
  vendor/maplibre/package/dist vendor/deck/package/dist.min.js 2026-10-29
```
