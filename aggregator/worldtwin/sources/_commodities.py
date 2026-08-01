"""Shared commodity taxonomy — the filter spine for Resources mode.

Every commodity has:
  - id: short slug
  - name: display name
  - hs: list of HS 4-digit codes (Comtrade cmdCode)
  - category: parent category (8 top-level)
  - color: hex colour from the Okabe-Ito palette
  - icon: Lucide icon name
  - unit: natural unit for display
"""

# 8 parent categories use Okabe-Ito CVD-safe palette
CATEGORIES = {
    "energy":       {"name": "Energy",          "color": "#E69F00", "icon": "fuel"},
    "agri":         {"name": "Agriculture",     "color": "#009E73", "icon": "wheat"},
    "metals":       {"name": "Metals & Ores",   "color": "#D55E00", "icon": "gem"},
    "tech":         {"name": "Tech & Semis",    "color": "#0072B2", "icon": "cpu"},
    "chemicals":    {"name": "Chemicals",       "color": "#CC79A7", "icon": "flask-conical"},
    "manufactures": {"name": "Manufactures",    "color": "#56B4E9", "icon": "factory"},
    "textiles":     {"name": "Textiles",        "color": "#F0E442", "icon": "shirt"},
    "other":        {"name": "Other",           "color": "#999999", "icon": "package"},
}

# Commodity list — HS codes from UN Comtrade HS classification.
# Each entry: (id, name, category, [hs4 codes], unit_hint, icon)
COMMODITIES = [
    # ====== ENERGY ======
    ("crude_oil",     "Crude Oil",            "energy", ["2709"],                 "$/bbl",   "droplet"),
    ("refined_oil",   "Refined Petroleum",    "energy", ["2710"],                 "$",       "fuel"),
    ("natural_gas",   "Natural Gas & LNG",    "energy", ["2711"],                 "$/MMBtu", "wind"),
    ("coal",          "Coal",                 "energy", ["2701", "2702", "2704"], "$/t",     "mountain"),
    ("uranium",       "Uranium",              "energy", ["2844"],                 "$/lb",    "atom"),
    ("electricity",   "Electricity",          "energy", ["2716"],                 "$/MWh",   "zap"),
    # ====== AGRICULTURE ======
    ("wheat",         "Wheat",                "agri", ["1001"],                 "$/t",  "wheat"),
    ("rice",          "Rice",                 "agri", ["1006"],                 "$/t",  "wheat"),
    ("corn",          "Corn / Maize",         "agri", ["1005"],                 "$/t",  "wheat"),
    ("soybeans",      "Soybeans",             "agri", ["1201"],                 "$/t",  "sprout"),
    ("palm_oil",      "Palm Oil",             "agri", ["1511"],                 "$/t",  "leaf"),
    ("coffee",        "Coffee",               "agri", ["0901"],                 "$/lb", "coffee"),
    ("cocoa",         "Cocoa",                "agri", ["1801", "1803", "1804"], "$/t",  "candy"),
    ("sugar",         "Sugar",                "agri", ["1701"],                 "$/lb", "candy"),
    ("beef",          "Beef & Veal",          "agri", ["0201", "0202"],         "$/t",  "beef"),
    ("pork",          "Pork",                 "agri", ["0203"],                 "$/t",  "ham"),
    ("fish",          "Fish & Seafood",       "agri", ["0302", "0303", "0304", "0306"], "$/t", "fish"),
    ("dairy",         "Dairy",                "agri", ["0401", "0402", "0406"], "$/t",  "milk"),
    ("fruits",        "Fruits",               "agri", ["0803", "0805", "0806", "0808"], "$/t", "apple"),
    ("cotton",        "Cotton",               "agri", ["5201", "5203"],         "$/lb", "shirt"),
    # ====== METALS & ORES ======
    ("iron_ore",      "Iron Ore",             "metals", ["2601"],            "$/t",  "mountain"),
    ("steel",         "Steel",                "metals", ["7208", "7209", "7210", "7214", "7222"], "$/t", "factory"),
    ("copper",        "Copper",               "metals", ["7403", "2603"],    "$/lb", "gem"),
    ("aluminum",      "Aluminum",             "metals", ["7601", "2606"],    "$/t",  "gem"),
    ("nickel",        "Nickel",               "metals", ["7502", "2604"],    "$/t",  "gem"),
    ("zinc",          "Zinc",                 "metals", ["7901", "2608"],    "$/t",  "gem"),
    ("lead",          "Lead",                 "metals", ["7801", "2607"],    "$/t",  "gem"),
    ("tin",           "Tin",                  "metals", ["8001", "2609"],    "$/t",  "gem"),
    ("gold",          "Gold",                 "metals", ["7108"],            "$/oz", "coins"),
    ("silver",        "Silver",               "metals", ["7106"],            "$/oz", "coins"),
    ("platinum",      "Platinum & Palladium", "metals", ["7110"],            "$/oz", "coins"),
    ("diamonds",      "Diamonds & Gems",      "metals", ["7102", "7103"],    "$/ct", "gem"),
    ("lithium",       "Lithium (Li2CO3 etc)", "metals", ["2836", "2530"],    "$/t",  "battery"),
    ("rare_earths",   "Rare Earth Elements",  "metals", ["2805", "2846"],    "$/t",  "atom"),
    ("cobalt",        "Cobalt",               "metals", ["8105", "2605"],    "$/lb", "battery"),
    # ====== TECH & SEMICONDUCTORS ======
    ("semiconductors","Semiconductors",      "tech", ["8542", "8541"],      "$", "cpu"),
    ("phones",        "Phones & Telecom",    "tech", ["8517"],              "$", "smartphone"),
    ("computers",     "Computers",           "tech", ["8471"],              "$", "monitor"),
    ("displays",      "Displays & LCDs",     "tech", ["8528"],              "$", "monitor"),
    # ====== MANUFACTURES / MACHINERY ======
    ("cars",          "Cars (passenger)",    "manufactures", ["8703"],          "$", "car"),
    ("trucks",        "Trucks",              "manufactures", ["8704"],          "$", "truck"),
    ("aircraft",      "Aircraft",            "manufactures", ["8802", "8803"],  "$", "plane"),
    ("ships",         "Ships",               "manufactures", ["8901", "8906"],  "$", "ship"),
    ("machinery",     "Industrial Machinery","manufactures", ["8479", "8431"],  "$", "settings"),
    # ====== CHEMICALS ======
    ("fertilizers",   "Fertilizers",         "chemicals", ["3102", "3104", "3105"], "$/t", "sprout"),
    ("pharma",        "Pharmaceuticals",     "chemicals", ["3003", "3004"],    "$", "pill"),
    ("plastics",      "Plastics",            "chemicals", ["3901", "3902", "3907"], "$/t", "package"),
    # ====== TEXTILES ======
    ("apparel",       "Apparel",             "textiles", ["6104", "6110", "6203"], "$", "shirt"),
    ("footwear",      "Footwear",            "textiles", ["6403"],            "$", "footprints"),
    # ====== OTHER ======
    ("timber",        "Timber / Wood",       "other", ["4403", "4407"],      "$/m3", "tree-pine"),
    ("paper",         "Paper",               "other", ["4802", "4810"],      "$/t",  "file-text"),
]

# Build fast lookups
BY_ID = {c[0]: {"id": c[0], "name": c[1], "category": c[2], "hs": c[3], "unit": c[4], "icon": c[5]} for c in COMMODITIES}
HS_TO_COMMODITY = {}
for c in COMMODITIES:
    for hs in c[3]:
        HS_TO_COMMODITY[hs] = c[0]


def all_hs_codes():
    out = []
    for c in COMMODITIES:
        out.extend(c[3])
    return sorted(set(out))


def hs_to_commodity_id(hs_code):
    # Accept full HS6 by truncating to 4
    hs4 = str(hs_code)[:4]
    return HS_TO_COMMODITY.get(hs4)


def all_categories():
    return [{"id": k, **v} for k, v in CATEGORIES.items()]


def all_commodities():
    return [BY_ID[cid] for cid in BY_ID]
