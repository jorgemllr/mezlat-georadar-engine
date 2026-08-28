"""
MESLATT — Commercial Cluster & Probe Extractor V4
==================================================

Reads `api_budget_allocation_v4.json` (output of Step 1) and determines the
**exact geographic coordinates** where each radar probe should be placed inside
each city.

Strategy per city type:
  - Mexican cities  → Query the INEGI DENUE Parquet. Assign each establishment
                      to an H3 hexagon (resolution 8, ~460 m diameter). Sort
                      hexagons by establishment count descending. The top N
                      hexagons become the radar probes, where N = max_probes
                      allocated to that city in Step 1.
  - International   → No DENUE data available. Generate probes via concentric
                      H3 rings expanding outward from the city's geographic
                      center until max_probes is reached.

Surplus redistribution:
  If a city has fewer qualifying DENUE hexagons than its allocated max_probes,
  the unused probes are rolled over to the next city in the same pool (Mexico
  or international) rather than being wasted.

Output:
  scripts/allocation_v4/commercial_clusters_v4.json
"""

import json
import math
import unicodedata
import duckdb
import h3
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent.parent.parent
DATASETS    = BASE_DIR / "Datasets"
V4_DIR      = BASE_DIR / "scripts" / "allocation_v4"

PARQUET_FILE       = DATASETS / "denue_mexico.parquet"
ALLOCATION_V4_FILE = V4_DIR   / "api_budget_allocation_v4.json"
CLUSTERS_V4_FILE   = V4_DIR   / "commercial_clusters_v4.json"

# ── H3 settings ───────────────────────────────────────────────────────────────
H3_RESOLUTION       = 8     # ~460 m hex diameter — good balance for a city scan
MIN_BIZ_PER_HEX     = 3     # Hexagons with fewer than this many businesses are skipped
ALL_CLUSTERS_VISUAL_CAP = 200  # Max hexagons rendered per city on the map (visual only)
                               # Does NOT limit radar_probes — those are capped by max_probes

# ── Recommended API search radius (stored in output for the pipeline to read) ─
API_SEARCH_RADIUS_M = 375   # 375 m radius from probe centroid.
                            # H3 res-8 apothem ≈ 400 m, vertex ≈ 461 m.
                            # 375 m covers ~90 % of the hex with minimal
                            # overlap into adjacent hexes (~10 m at edges only).

# ── Per-niche DENUE keyword map ───────────────────────────────────────────────
# Maps each Google Places includedType to a list of Spanish keyword fragments
# that match real Mexican business names in the DENUE dataset.
# Used both for the broad filter query and for per-hex niche breakdown counting.
NICHE_KEYWORD_MAP: dict[str, list[str]] = {
    "roofing_contractor":  [
        "impermeabiliz", "techo", "tejado", "azotea", "techador",
        "lamina", "impermeabilizador", "cubierta", "membranas impermeables",
    ],
    "plumber": [
        "plomer", "fontaner", "instalacion hidraulica", "hidro",
        "tuberia", "sanitario", "drenaje", "agua potable", "cisterna",
        "desazolve", "instalacion sanitaria",
    ],
    "hvac_contractor": [
        "aire acondicionado", "refrigeracion", "clima", "hvac",
        "ventilacion", "minisplit", "calefaccion", "enfriamiento",
        "climatizacion", "sistema de clima", "aire y calefaccion",
    ],
    "lawyer": [
        "abogad", "bufete", "licenciad", "notari", "juridic",
        "despacho juridico", "firma legal", "consultorio juridico",
        "asesor legal", "derecho", "abogados asociados",
    ],
    "electrician": [
        "electric", "instalacion electrica", "electrotecnia",
        "tablero", "cableado", "iluminacion industrial",
        "tecnico electricista", "planta electrica", "transformador",
    ],
    "car_repair": [
        "taller", "mecanica", "servicio automotriz", "autoservicio",
        "refaccion", "vulcanizadora", "llantera", "diagnostico automotriz",
        "alineacion", "frenos", "hojalateria", "pintura automotriz",
        "electrico automotriz", "servicio automotor",
    ],
    "locksmith": [
        "cerrajer", "llaves", "duplicado de llave", "candado",
        "chapas", "seguridad en puertas", "herreria de llaves",
        "apertura de puertas", "cofres de seguridad",
    ],
    "dentist": [
        "dentist", "dental", "odontolog", "clinica dental",
        "ortodoncia", "endodoncia", "consultorio dental",
        "protesis dental", "implante dental", "blanqueamiento dental",
    ],
    "physiotherapist": [
        "fisiotera", "rehabilitacion", "terapia fisica",
        "kinesiolog", "quiropractic", "terapia manual",
        "fisiatria", "medicina fisica", "centro de rehabilitacion",
    ],
    "veterinary_care": [
        "veterinari", "clinica veterinaria", "hospital veterinario",
        "medico veterinario", "pet shop", "tienda de mascotas",
        "grooming", "estetica canina", "peluqueria canina",
    ],
    "medical_clinic": [
        "medic", "clinica", "hospital", "consultorio medico",
        "medicina general", "especialist", "centro medico",
        "laboratorio clinico", "farmacia con consultorio", "urgencias",
    ],
    "real_estate_agency": [
        "inmobiliaria", "bienes raices", "propiedades",
        "desarrollo inmobiliario", "agencia inmobiliaria",
        "venta de casas", "renta de departamentos", "asesores inmobiliarios",
        "plusvalia", "bienes inmuebles",
    ],
    "spa": [
        "spa", "masajes", "relajacion", "tratamiento corporal",
        "sauna", "jacuzzi", "masoterapia", "aromaterapia",
        "centro de bienestar", "terapia de relajacion",
    ],
    "accounting": [
        "contador", "contabilidad", "despacho contable",
        "fiscal", "auditoria", "nomina", "asesoria contable",
        "declaraciones fiscales", "sat", "regimen fiscal",
    ],
    "night_club": [
        "antro", "club nocturno", "discoteca", "table dance",
        "botanero", "cantina", "bar de copas", "karaoke bar",
        "salon de fiestas", "night club",
    ],
    "sports_club": [
        "cancha", "club deportivo", "deportivo", "centro deportivo",
        "padel", "tenis", "futbol", "basquetbol", "voleibol",
        "campo deportivo", "pista de atletismo",
    ],
    "barber_shop": [
        "barberia", "barbero", "corte caballeros", "estilista hombre",
        "peluqueria", "navaja", "corte de cabello", "barber",
    ],
    "dance_studio": [
        "academia de baile", "escuela de baile", "clases de baile",
        "ballet", "salsa", "danza", "baile folklorico",
        "estudio de baile", "danza contemporanea", "ritmos latinos",
    ],
    "beauty_salon": [
        "estetica", "salon de belleza", "unas", "pestanas",
        "pedicure", "manicure", "depilacion", "tinte de cabello",
        "extensiones", "maquillaje profesional", "nails",
    ],
    "gym": [
        "gym", "gimnasio", "crossfit", "fitness", "musculacion",
        "ejercicio", "entrenamiento", "box", "cardio",
        "sala de pesas", "funcional", "bodybuilding",
    ],
    "florist": [
        "floreria", "florista", "arreglos florales", "flores",
        "ramos", "decoracion floral", "bouquet", "plantas ornamentales",
        "centro de mesa", "coronas de flores",
    ],
    "restaurant": [
        "restaur", "fonda", "comedor", "marisqueria", "hamburgues",
        "taqueria", "pizzeria", "cocina economica", "birrieria",
        "pozoleria", "tortas", "mariscos", "sushi", "cenadurias",
        "barbacoa", "carnitas", "asadero", "loncheria",
    ],
    "bakery": [
        "panaderia", "pasteleria", "reposteria", "pan artesanal",
        "pastel", "cake", "galletas", "pan de caja",
        "chocolate artesanal", "donuts",
    ],
    "cafe": [
        "cafe", "cafeteria", "cappuccino", "expresso", "coffee",
        "barista", "cafe de olla", "cafe organico",
        "brunch", "te y cafe",
    ],
}

# Flat regex combining ALL niche keywords — used for the initial broad DENUE filter.
# DuckDB will apply this to business names before H3 grouping.
_all_keywords = sorted(
    {kw for keywords in NICHE_KEYWORD_MAP.values() for kw in keywords},
    key=len, reverse=True   # Longer patterns first to avoid partial-match priority issues
)
DENUE_KEYWORD_PATTERN = "(" + "|".join(_all_keywords) + ")"


# ── Helpers ───────────────────────────────────────────────────────────────────

def norm(s: str) -> str:
    """Lowercase, strip accents, trim whitespace."""
    if not s:
        return ""
    s = str(s).lower().strip()
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


# City name → DENUE search target mapping.
# SimpleMaps uses English / simplified names; DENUE uses official Spanish names.
ALIAS_MAP = {
    "mexico city":               "ciudad de mexico",
    "cdmx":                      "ciudad de mexico",
    "leon de los aldama":        "leon",
    "toluca":                    "toluca",          # SimpleMaps uses "Toluca", DENUE has "Toluca de Lerdo"
    "toluca de lerdo":           "toluca",
    "heroica puebla de zaragoza":"puebla",
    "santiago de queretaro":     "queretaro",
    "cancun":                    "benito juarez",
    "ecatepec de morelos":       "ecatepec",
    "ecatepec":                  "ecatepec",
    "nezahualcoyotl":            "nezahualcoyotl",
    "ciudad nezahualcoyotl":     "nezahualcoyotl",
    "naucalpan de juarez":       "naucalpan",
    "naucalpan":                 "naucalpan",
}

# Maximum probes to place via H3 concentric fallback when a Mexican city has
# no DENUE data. Without this cap, the ring expansion fills the entire surplus
# from previous cities into a single city blindly.
MX_H3_FALLBACK_CAP = 50

# Cities whose administrative boundaries span a larger municipality;
# search by state name instead of city name.
SEARCH_BY_STATE = {"ciudad de mexico"}

# Manual cities that are sub-municipal zones of a larger city;
# use a tight geographic bounding box instead of city-name matching.
TIGHT_BBOX_CITIES = {"juriquilla", "el pueblito", "el pueblito (centro)"}
TIGHT_BBOX_RADIUS_KM = 5.0    # ± 5 km around the coordinates
DEFAULT_BBOX_RADIUS_KM = 12.0 # ± 60 km for standard city search


def build_bbox(lat: float, lng: float, radius_km: float) -> tuple:
    """Returns (lat_min, lat_max, lng_min, lng_max) for a square bounding box."""
    d_lat = radius_km / 111.0
    d_lng = radius_km / (111.0 * math.cos(math.radians(lat)))
    return lat - d_lat, lat + d_lat, lng - d_lng, lng + d_lng


# ── International probe generator (concentric H3 rings) ───────────────────────

def generate_intl_probes(city_name: str, country: str,
                          lat: float, lng: float,
                          max_probes: int) -> list:
    """
    Generates H3 probes for a non-Mexican city by expanding outward from the
    city center in concentric rings until max_probes is reached.
    """
    center_hex     = h3.latlng_to_cell(lat, lng, H3_RESOLUTION)
    visited        = set()
    radar_probes   = []
    ring_k         = 0

    while len(radar_probes) < max_probes:
        ring = h3.grid_ring(center_hex, ring_k)
        if not ring:
            # Fallback for H3 pentagon distortion edge cases
            ring = h3.k_ring(center_hex, ring_k) - visited

        for cell in ring:
            if len(radar_probes) >= max_probes:
                break
            if cell not in visited:
                visited.add(cell)
                c_lat, c_lng = h3.cell_to_latlng(cell)
                radar_probes.append({
                    "cluster_id":        f"intl_{norm(city_name).replace(' ', '_')}_{cell}",
                    "city":              city_name,
                    "country":           country,
                    "h3_index":          cell,
                    "centroid_lat":      c_lat,
                    "centroid_lng":      c_lng,
                    "boundary":          list(h3.cell_to_boundary(cell)),
                    "establishment_count": 50,   # Placeholder — no DENUE for intl cities
                    "establishments_sample": [],
                })
        ring_k += 1

    return radar_probes


# ── Mexican DENUE cluster extractor ───────────────────────────────────────────

def extract_denue_clusters(city_name: str, lat: float, lng: float,
                            max_probes: int,
                            global_probe_set: set) -> dict:
    """
    Queries the DENUE Parquet for a Mexican city, groups results into H3
    hexagons, and selects the densest hexagons as radar probes.

    Parameters
    ----------
    city_name       : SimpleMaps city name (used for alias lookup).
    lat, lng        : City center coordinates (used for bounding box filter).
    max_probes      : Maximum number of probes to place for this city.
    global_probe_set: Set of already-placed H3 cell IDs (prevents duplicates
                      across cities that share hexagons near their borders).

    Returns a dict with keys: all_clusters, radar_probes, budget_summary.
    """
    if not PARQUET_FILE.exists():
        return {}

    clean = norm(city_name)
    target = ALIAS_MAP.get(clean, clean)

    # Build bounding box
    radius = TIGHT_BBOX_RADIUS_KM if target in TIGHT_BBOX_CITIES else DEFAULT_BBOX_RADIUS_KM
    lat_min, lat_max, lng_min, lng_max = build_bbox(lat, lng, radius)

    con = duckdb.connect(database=":memory:")

    try:
        # Pull all relevant businesses within the bounding box first (fast path)
        bbox_query = f"""
            SELECT
                establishment_id, business_name, legal_name,
                city, state, latitude, longitude, phone, email, website
            FROM '{PARQUET_FILE}'
            WHERE latitude  BETWEEN {lat_min} AND {lat_max}
              AND longitude BETWEEN {lng_min} AND {lng_max}
              AND latitude  IS NOT NULL
              AND longitude IS NOT NULL
              AND regexp_matches(LOWER(business_name), '{DENUE_KEYWORD_PATTERN}')
        """
        df = con.execute(bbox_query).df()
    except Exception as exc:
        print(f"   ⚠️  DuckDB error for {city_name}: {exc}")
        return {}

    if df.empty:
        return {}

    # Pure geographic filter: we completely bypass INEGI city naming restrictions.
    # The bounding box (12km standard, 5km tight) is our only boundary!
    if df.empty:
        return {}

    # Assign each row to its H3 hexagon
    df["h3_index"] = df.apply(
        lambda r: h3.latlng_to_cell(r["latitude"], r["longitude"], H3_RESOLUTION),
        axis=1,
    )
    # Pre-lowercase business names for fast niche matching
    df["biz_lower"] = df["business_name"].apply(
        lambda n: norm(str(n)) if n else ""
    )

    # Redistributed Batch assignment (balancing highly dense niches)
    BATCH_NICHES = {
        1: {"restaurant", "plumber", "electrician", "hvac_contractor", 
            "roofing_contractor", "car_repair", "locksmith"},
        2: {"cafe", "bakery", "dentist", "medical_clinic", "veterinary_care", 
            "physiotherapist", "lawyer", "accounting"},
        3: {"beauty_salon", "barber_shop", "gym", "sports_club", "spa", 
            "dance_studio", "night_club", "real_estate_agency", "florist"},
    }

    # Group by hexagon and compute niche breakdown
    all_clusters = []
    for h3_idx, group in df.groupby("h3_index"):
        if len(group) < MIN_BIZ_PER_HEX:
            continue
        c_lat, c_lng = h3.cell_to_latlng(h3_idx)

        # Count businesses per niche using keyword matching on business names
        niche_breakdown: dict[str, int] = {}
        for niche, keywords in NICHE_KEYWORD_MAP.items():
            count = int(group["biz_lower"].apply(
                lambda name: any(kw in name for kw in keywords)
            ).sum())
            if count > 0:
                niche_breakdown[niche] = count

        # Disable adaptive filtering: Force all 3 batches to run on every qualifying hex
        # to guarantee we don't miss high-ticket trades that DENUE is blind to.
        active_batches = [1, 2, 3]

        all_clusters.append({
            "cluster_id":         f"{norm(city_name).replace(' ', '_')}_{h3_idx}",
            "city":               city_name,
            "country":            "Mexico",
            "h3_index":           h3_idx,
            "centroid_lat":       c_lat,
            "centroid_lng":       c_lng,
            "boundary":           list(h3.cell_to_boundary(h3_idx)),
            "establishment_count": len(group),
            "niche_breakdown":    niche_breakdown,
            "active_batches":     active_batches,   # e.g. [1, 3] → only run batches 1 and 3
            "api_search_radius_m": API_SEARCH_RADIUS_M,
            "establishments_sample": (
                group[["business_name", "phone", "email"]]
                .head(5)
                .to_dict(orient="records")
            ),
        })

    # Sort densest first — these are the probes we want to scan first
    all_clusters.sort(key=lambda x: x["establishment_count"], reverse=True)


    # Select top N hexagons as radar probes (no cap here — capped by max_probes)
    radar_probes = []
    
    # ── INJECT MANUAL H3 PROBES BEFORE ANYTHING ELSE ──
    MANUAL_PROBES_INJECTIONS = {
        "Juriquilla": [
            "884983cabbfffff", # Parque Juriquilla (El de 3 neg. arriba)
            "884983ca83fffff", # Antea / Uptown (Hexágono verdadero a la izquierda del de 7)
        ]
    }
    if city_name in MANUAL_PROBES_INJECTIONS:
        manual_hexes = MANUAL_PROBES_INJECTIONS[city_name]
        for c in all_clusters:
            if c["h3_index"] in manual_hexes and c["h3_index"] not in global_probe_set:
                radar_probes.append(c)
                global_probe_set.add(c["h3_index"])
        
        # If the manual hexes were not in DENUE at all (empty), create them synthetically
        existing_in_denue = {c["h3_index"] for c in radar_probes}
        for manual_hex in manual_hexes:
            if manual_hex not in existing_in_denue and manual_hex not in global_probe_set:
                c_lat, c_lng = h3.cell_to_latlng(manual_hex)
                synthetic_probe = {
                    "cluster_id":         f"{norm(city_name).replace(' ', '_')}_{manual_hex}",
                    "city":               city_name,
                    "country":            "Mexico",
                    "h3_index":           manual_hex,
                    "centroid_lat":       c_lat,
                    "centroid_lng":       c_lng,
                    "boundary":           list(h3.cell_to_boundary(manual_hex)),
                    "establishment_count": 50, # Synthetic fallback weight
                    "niche_breakdown":    {},
                    "active_batches":     [1, 2, 3],
                    "api_search_radius_m": API_SEARCH_RADIUS_M,
                    "establishments_sample": []
                }
                radar_probes.append(synthetic_probe)
                global_probe_set.add(manual_hex)
                # Also add to all_clusters so they render the hexagon
                all_clusters.append(synthetic_probe)
                
    # Now continue filling the rest normally until max_probes
    for cluster in all_clusters:
        if len(radar_probes) >= max_probes:
            break
        if cluster["h3_index"] not in global_probe_set:
            radar_probes.append(cluster)
            global_probe_set.add(cluster["h3_index"])


    actual = len(radar_probes)

    # Build the visual cluster list so every radar_probe always has a hexagon on
    # the map. Strategy:
    #   1. Start with all radar_probes (guaranteed to be rendered).
    #   2. Fill remaining visual slots (up to ALL_CLUSTERS_VISUAL_CAP) with
    #      non-probe hexagons from all_clusters, ordered by density.
    # This prevents the "red dot without hexagon" artifact when a city has more
    # probes than ALL_CLUSTERS_VISUAL_CAP.
    probe_hex_ids = {c["h3_index"] for c in radar_probes}
    non_probe_hexes = [c for c in all_clusters if c["h3_index"] not in probe_hex_ids]
    extra_slots = max(0, ALL_CLUSTERS_VISUAL_CAP - actual)
    visual_clusters = radar_probes + non_probe_hexes[:extra_slots]

    return {
        "all_clusters":  visual_clusters,   # radar_probes first, then fill to cap
        "radar_probes":  radar_probes,
        "budget_summary": {
            "max_probes_allocated": max_probes,
            "actual_probes_placed": actual,
            "probes_unused":        max_probes - actual,
            "phase1_calls_planned": actual * 3,
            "phase2_calls_planned": 0,          # Filled in during pipeline execution
        },
    }


# ── Main routine ──────────────────────────────────────────────────────────────

def run_cluster_extraction_v4():
    print("🚀 MESLATT — Cluster & Probe Extractor V4 (Mexico-First, DENUE-Driven)")
    V4_DIR.mkdir(parents=True, exist_ok=True)

    if not ALLOCATION_V4_FILE.exists():
        print(f"❌ Allocation file not found: {ALLOCATION_V4_FILE}")
        print("   Run mcda_allocator_v4.py first.")
        return {}

    with open(ALLOCATION_V4_FILE, "r", encoding="utf-8") as f:
        alloc_data = json.load(f)

    cities = alloc_data.get("cities", [])
    print(f"📋 Processing {len(cities)} allocated cities...")

    global_probe_set = set()   # Tracks H3 cells already claimed by any city
    all_clusters     = {}
    total_probes     = 0
    mx_probes        = 0
    intl_probes      = 0

    for city in cities:
        name       = city["city"]
        country    = city.get("country", "Mexico")
        admin_name = city.get("admin_name", "")
        lat        = city.get("lat", 0)
        lng        = city.get("lng", 0)
        max_probes = city.get("max_probes", 0)
        if name == 'Juriquilla':
            max_probes = 25

        if max_probes <= 0:
            continue

        # ── Place probes ──────────────────────────────────────────────────────
        if country == "Mexico":
            result = extract_denue_clusters(name, lat, lng, max_probes, global_probe_set)

            if result and result.get("radar_probes"):
                all_clusters[name] = result
                actual = len(result["radar_probes"])
                print(f"   🎯 {name:<30} {actual:>3} probes  "
                      f"(DENUE hex, max={max_probes}, "
                      f"density clusters: {len(result['all_clusters'])})")
            else:
                # No DENUE match.
                # STRATEGY RULE: Only allow H3 Fallback for Estado de Mexico (because its DENUE data is missing).
                # If it's any other Mexican state, skip it (because it means it's a true ghost town).
                # Check if it's an Edomex city by name (since admin_name mapping failed in MCDA)
                edomex_cities = [
                    "Ecatepec", "Nezahualcoyotl", "Ciudad Nezahualcoyotl", "Naucalpan de Juarez", "Naucalpan", 
                    "Toluca", "Tlalnepantla", "Chimalhuacan", "Tultitlan", "Cuautitlan Izcalli", "Ixtapaluca",
                    "Atizapan de Zaragoza", "Valle de Chalco Solidaridad", "Chalco", "Chicoloapan", "La Paz",
                    "Tecamac", "Zumpango", "Huehuetoca", "Texcoco", "Metepec", "Zinacantepec", "San Mateo Atenco",
                    "San Felipe del Progreso", "San Jose del Rincon Centro", "Tepotzotlan", "Santa Catarina Otzolotepec",
                    "Teoloyucan", "Jocotitlan", "Coyula", "Santiago Tianguistenco", "Temascalcingo", "Valle de Bravo",
                    "Acambay", "San Jose Villa de Allende", "Tenancingo", "Jilotepec", "Villa Guerrero", "Melchor Ocampo", "Coacalco"
                ]
                if name in edomex_cities:
                    print(f"   ⚠️  {name}: no DENUE data (Edomex Bug) → H3 fallback "
                          f"(capped at {MX_H3_FALLBACK_CAP})")
                    probes = generate_intl_probes(
                        name, country, lat, lng, min(max_probes, MX_H3_FALLBACK_CAP)
                    )
                    actual = len(probes)
                    # Use probes as all_clusters so every red dot gets a hexagon.
                    # generate_intl_probes already computes boundary for each probe.
                    all_clusters[name] = {
                        "all_clusters":  probes,
                        "radar_probes":  probes,
                        "budget_summary": {
                            "max_probes_allocated": max_probes,
                            "actual_probes_placed": actual,
                            "probes_unused":        max_probes - actual,
                            "phase1_calls_planned": actual * 3,
                            "phase2_calls_planned": 0,
                            "note": "H3 concentric fallback — Edomex DENUE missing",
                        },
                    }
                    mx_probes += actual
                else:
                    print(f"   🚫 {name}: no DENUE data in {admin_name} → Fallback blocked (Ghost Town)")

        else:
            # International city — always use concentric H3 rings.
            # Use probes as all_clusters so every red dot gets a hexagon.
            probes = generate_intl_probes(name, country, lat, lng, max_probes)
            actual = len(probes)
            all_clusters[name] = {
                "all_clusters":  probes,
                "radar_probes":  probes,
                "budget_summary": {
                    "max_probes_allocated": max_probes,
                    "actual_probes_placed": actual,
                    "probes_unused":        max_probes - actual,
                    "phase1_calls_planned": actual * 3,
                    "phase2_calls_planned": 0,
                },
            }
            intl_probes += actual
            print(f"   🌍 {name:<30} {actual:>3} probes  (H3 rings, {country})")

        total_probes += actual

        # Write actual counts to a SEPARATE field so we never corrupt the
        # Step 1 planned budget (max_probes). The dashboard reads both:
        # max_probes = what Step 1 planned, actual_probes = what Step 2 placed.
        city["actual_probes"]       = actual
        city["actual_phase1_calls"] = actual * 3
        city["phase2_calls"]        = 0
        est_biz = actual * 60   # 20 results × 3 batches per probe
        city["actual_projections"] = {
            "est_raw_businesses":   est_biz,
            "est_hot_leads_phase2": int(est_biz * 0.05),
        }

    # Persist the updated allocation (with real probe counts) for the dashboard
    with open(ALLOCATION_V4_FILE, "w", encoding="utf-8") as f:
        json.dump(alloc_data, f, indent=2, ensure_ascii=False)

    with open(CLUSTERS_V4_FILE, "w", encoding="utf-8") as f:
        json.dump(all_clusters, f, indent=2, ensure_ascii=False)


    # ── Summary ───────────────────────────────────────────────────────────────
    total_ph1 = total_probes * 3
    print(f"""
╔══════════════════════════════════════════════════════════╗
║        Cluster Extractor V4 — Placement Summary          ║
╠══════════════════════════════════════════════════════════╣
║  Cities processed  : {len(all_clusters):>4}                               ║
║  Mexico probes     : {mx_probes:>4}                               ║
║  International     : {intl_probes:>4}                               ║
║  Total probes      : {total_probes:>4}                               ║
║  Phase 1 calls     : {total_ph1:>5} (= probes × 3 batches)          ║
╚══════════════════════════════════════════════════════════╝
    """)
    print(f"💾 Saved: {CLUSTERS_V4_FILE}")
    return all_clusters


if __name__ == "__main__":
    run_cluster_extraction_v4()
