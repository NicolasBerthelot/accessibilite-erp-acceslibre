"""Construit le site de la carte de l'accessibilité des ERP (Acceslibre), avec fiches complètes.

Usage : python3 -I build.py <fichier.parquet> <dossier_sortie> <template.html> <maplibre_dir> <deck.min.js> <date AAAA-MM-JJ>

Produit dans <dossier_sortie> :
  index.html                      la page
  lib/                            MapLibre GL JS et deck.gl
  donnees/erp.json.gz             établissements (positions, noms, adresses, liens)
  donnees/criteres.bin.gz         critères d'accessibilité codés (matrice uint8 par colonne)
"""
import os
import shutil
import gzip
import json
import re
import sys
import unicodedata

import duckdb

src, outdir, template_path, mldir, deck_path, extract_date = sys.argv[1:7]

con = duckdb.connect()
con.execute(f"CREATE TABLE raw AS SELECT * FROM read_parquet('{src}')")
cols = [r[0] for r in con.execute("DESCRIBE raw").fetchall()]
colset = set(cols)
print("colonnes :", len(cols))

# Colonnes traitées à part (identité, adresse, liens) ; tout le reste devient un critère codé
IDENTITY = {"id", "name", "postal_code", "commune", "numero", "voie", "lieu_dit", "code_insee",
            "activite", "longitude", "latitude", "widget_code", "rpa", "web_url"}
SPARSE_STR = ["site_internet", "contact_url", "registre_url", "rnb_id", "siret"]
CODED = [c for c in cols if c not in IDENTITY and c not in SPARSE_STR]


def b(name):
    if name not in colset:
        return "NULL"
    return (f"CASE WHEN lower(CAST({name} AS VARCHAR)) IN ('true','t','1') THEN 1 "
            f"WHEN lower(CAST({name} AS VARCHAR)) IN ('false','f','0') THEN 0 END")


def s(name):
    return f"NULLIF(trim(CAST({name} AS VARCHAR)), '')" if name in colset else "NULL"


con.execute(f"""
CREATE TABLE erp AS
SELECT row_number() OVER () AS rid, *,
  TRY_CAST(longitude AS DOUBLE) AS _lon, TRY_CAST(latitude AS DOUBLE) AS _lat,
  CASE
    WHEN {b('entree_plain_pied')} = 1 THEN 0
    WHEN {b('entree_pmr')} = 1 OR {b('entree_ascenseur')} = 1
         OR lower({s('entree_marches_rampe')}) IN ('fixe', 'amovible') THEN 1
    WHEN {b('entree_plain_pied')} = 0 THEN 2
    ELSE 3 END AS _cat
FROM raw
""")
total_raw = con.execute("SELECT count(*) FROM erp").fetchone()[0]
con.execute("DELETE FROM erp WHERE _lon IS NULL OR _lat IS NULL OR _lon NOT BETWEEN -180 AND 180 "
            "OR _lat NOT BETWEEN -90 AND 90 OR (_lon = 0 AND _lat = 0)")
total = con.execute("SELECT count(*) FROM erp").fetchone()[0]
print(f"lignes : {total_raw}, géolocalisées : {total}")

# Ordre d'affichage : non renseignés dessous, puis tri spatial (aucune catégorie favorisée)
order = "ORDER BY (_cat = 3) DESC, _lat DESC, _lon"
rows = con.execute(f"""
SELECT _lon, _lat, _cat, coalesce({s('activite')}, 'Non renseignée'), {s('name')}, {s('commune')},
       {s('postal_code')}, trim(concat_ws(' ', {s('numero')}, {s('voie')}, {s('lieu_dit')})),
       {s('web_url')}
FROM erp {order}""").fetchall()
N = len(rows)

acts_count = {}
for r in rows:
    acts_count[r[3]] = acts_count.get(r[3], 0) + 1
acts = sorted(acts_count, key=lambda a: (-acts_count[a], a))
act_idx = {a: k for k, a in enumerate(acts)}


def slugify(v):
    """Équivalent de django.utils.text.slugify (utilisé par Acceslibre)."""
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode("ascii")
    v = re.sub(r"[^\w\s-]", "", v.lower())
    return re.sub(r"[-\s]+", "-", v).strip("-_")


URL_PREFIX = "https://acceslibre.beta.gouv.fr/app/"
communes, com_idx = [], {}
uparts, upart_idx = [], {}
C = {k: [] for k in ["x", "y", "c", "a", "n", "m", "d", "uc", "ua", "ue"]}
url_ok = url_slug_eq = 0
for lon, lat, cat, act, nom, commune, cp, adr, url in rows:
    key = f"{commune or ''}|{cp or ''}"
    if key not in com_idx:
        com_idx[key] = len(communes)
        communes.append(key)
    C["x"].append(round(lon * 1e5))
    C["y"].append(round(lat * 1e5))
    C["c"].append(cat)
    C["a"].append(act_idx[act])
    C["n"].append(nom or "")
    C["m"].append(com_idx[key])
    C["d"].append(adr or "")
    # URL Acceslibre découpée : <commune>/a/<activité>/erp/<slug>/
    m = re.match(r"^" + re.escape(URL_PREFIX) + r"([^/]+)/a/([^/]+)/erp/([^/]+)/?$", url or "")
    if m:
        url_ok += 1
        parts = []
        for p in (m.group(1), m.group(2)):
            if p not in upart_idx:
                upart_idx[p] = len(uparts)
                uparts.append(p)
            parts.append(upart_idx[p])
        C["uc"].append(parts[0])
        C["ua"].append(parts[1])
        if m.group(3) == slugify(nom or ""):
            url_slug_eq += 1
            C["ue"].append(0)          # slug = slugify(nom) : recalculé dans le navigateur
        else:
            C["ue"].append(m.group(3))
    else:
        C["uc"].append(-1)
        C["ua"].append(-1)
        C["ue"].append(url or "")      # URL complète atypique (ou vide)
print(f"URL Acceslibre : {url_ok} au format attendu, dont {url_slug_eq} reconstruites depuis le nom")

# Parties d'URL : valeur par défaut par commune / par activité, exceptions éparses
from collections import Counter
for col, key_col, name in (("uc", "m", "comUrl"), ("ua", "a", "actUrl")):
    cnt = {}
    for kk, u in zip(C[key_col], C[col]):
        cnt.setdefault(kk, Counter())[u] += 1
    nkeys = max(C[key_col]) + 1
    default = [cnt[kk].most_common(1)[0][0] if kk in cnt else -1 for kk in range(nkeys)]
    idx, vals, prev = [], [], 0
    for r, (kk, u) in enumerate(zip(C[key_col], C[col])):
        if u != default[kk]:
            idx.append(r - prev)
            prev = r
            vals.append(u)
    C[col] = [idx, vals]
    C[name] = default
    print(f"  {col} : {len(vals)} exceptions")

for k in ("x", "y"):
    arr, prev, d = C[k], 0, []
    for v in arr:
        d.append(v - prev)
        prev = v
    C[k] = d

# Chaînes éparses (site, contact, registre, RNB, SIRET) : {champ: [indices delta, valeurs]}
sparse = {}
for f in SPARSE_STR:
    if f not in colset:
        continue
    expr = f"CAST(CAST({f} AS HUGEINT) AS VARCHAR)" if f == "siret" else s(f)
    vals = [r[0] for r in con.execute(f"SELECT {expr} FROM erp {order}").fetchall()]
    idx, v_out, prev = [], [], 0
    for k, v in enumerate(vals):
        if v:
            idx.append(k - prev)
            prev = k
            v_out.append(v)
    sparse[f] = [idx, v_out]
    print(f"  {f} : {len(v_out)} valeurs")

# Critères codés : dictionnaire par champ, matrice uint8 par colonne (0 = non renseigné)
dicts = {}
blob = bytearray()
for f in CODED:
    vals = [r[0] for r in con.execute(f'SELECT "{f}" FROM erp {order}').fetchall()]
    dvals, didx, codes = [None], {}, bytearray(N)
    for k, v in enumerate(vals):
        if v is None:
            continue
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if isinstance(v, str):
            t = v.strip()
            if t.startswith("["):
                try:
                    v = json.loads(t)
                except ValueError:
                    pass
            elif t in ("True", "False"):
                v = t == "True"
            if v == [] or v == "":
                continue
        hk = json.dumps(v, ensure_ascii=False, sort_keys=True)
        if hk not in didx:
            didx[hk] = len(dvals)
            dvals.append(v)
        codes[k] = didx[hk]
    if len(dvals) > 255:
        raise SystemExit(f"{f} : trop de valeurs distinctes ({len(dvals)})")
    dicts[f] = dvals
    blob += codes
print(f"critères codés : {len(CODED)} champs, matrice {len(blob)/1e6:.1f} Mo")

cat_counts = [0, 0, 0, 0]
for v in C["c"]:
    cat_counts[v] += 1

payload = {
    "acts": acts, "actCounts": [acts_count[a] for a in acts], "communes": communes,
    "uparts": uparts, "urlPrefix": URL_PREFIX, "cols": C, "sparse": sparse,
    "fields": CODED, "dicts": dicts, "total": total, "totalRaw": total_raw,
    "catCounts": cat_counts, "date": extract_date,
}
raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
os.makedirs(f"{outdir}/donnees", exist_ok=True)
os.makedirs(f"{outdir}/lib", exist_ok=True)
with gzip.open(f"{outdir}/donnees/erp.json.gz", "wb", compresslevel=9) as fh:
    fh.write(raw_json)
with gzip.open(f"{outdir}/donnees/criteres.bin.gz", "wb", compresslevel=9) as fh:
    fh.write(bytes(blob))
shutil.copy(f"{mldir}/maplibre-gl.js", f"{outdir}/lib/maplibre-gl.js")
shutil.copy(f"{mldir}/maplibre-gl.css", f"{outdir}/lib/maplibre-gl.css")
shutil.copy(deck_path, f"{outdir}/lib/deck.gl.min.js")
shutil.copy(template_path, f"{outdir}/index.html")
for f in ("donnees/erp.json.gz", "donnees/criteres.bin.gz", "index.html"):
    print(f"  {f} : {os.path.getsize(f'{outdir}/{f}')/1e6:.2f} Mo")
print(f"catégories {cat_counts}")
