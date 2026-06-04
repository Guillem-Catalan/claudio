TEAMS = {
    "Santander": {
        "active": True,
        "partner_names": {"santander", "banco santander", "santander bank", "santander españa"},
        "partner_domains": {"santander.com", "bancosantander.es", "gruposantander.com", "gruposantander.es"},
        "pbd": {
            "ines.rivera@factorial.co",
            "carlos.acosta@factorial.co",
            "marta.ruiz@factorial.co",
            "paula.gil@factorial.co",
            "david.soler@factorial.co",
            "lucia.garana@factorial.co",
            "nicolas.gonzalez@factorial.co",
        },
        "pae": {
            "xavier.fortuny@factorial.co",
            "jose.donis@factorial.co",
            "pol.bartolome@factorial.co",
            "roberto.moran@factorial.co",
            "beatriz.bravo@factorial.co",
            "joan.lorenzo@factorial.co",
            "joan.balana@factorial.co",
        },
    },
    "Telefónica": {
        "active": True,
        "partner_names": {"telefonica", "telefónica", "telefonica españa", "telefónica españa"},
        "partner_domains": {"telefonica.com", "telefonica.es"},
        "pbd": {
            "angel.hernandez@factorial.co",
            "jon.azconobieta@factorial.co",
            "maria.masoliver@factorial.co",
            "alejandro.soto@factorial.co",
        },
        "pae": {
            "david.clemente@factorial.co",
            "nerea.urien@factorial.co",
            "carlos.sanchez@factorial.co",
            "alejandro.soto@factorial.co",
            "joan.balana@factorial.co",
        },
    },
    "TIM": {
        "active": False,
        "partner_names": {"tim", "tim italia"},
        "partner_domains": {"sa.telecomitalia.it"},
        "pbd": set(),
        "pae": {
            "christian.lombardo@factorial.co",
            "edoardo.rapezzi@factorial.co",
            "emilio.fabbro@factorial.co",
            "nunzio.fumo@factorial.co",
        },
    },
    "TELEKOM": {
        "active": False,
        "partner_names": {"telekom", "deutsche telekom"},
        "partner_domains": {"telekom.de"},
        "pbd": set(),
        "pae": {
            "leonhard.zeus@factorial.co",
            "katrin.virtbauer@factorial.co",
        },
    },
}

# ── Derived sets (computed once at import) ───────────────────────────────────

ALL_PBD_EMAILS: set[str] = set()
ALL_PAE_EMAILS: set[str] = set()
ALL_REP_EMAILS: set[str] = set()
ALL_PARTNER_NAMES: set[str] = set()
ALL_PARTNER_DOMAINS: set[str] = set()

for _team in TEAMS.values():
    ALL_PBD_EMAILS |= _team["pbd"]
    ALL_PAE_EMAILS |= _team["pae"]
    ALL_REP_EMAILS |= _team["pbd"] | _team["pae"]
    ALL_PARTNER_NAMES |= _team["partner_names"]
    ALL_PARTNER_DOMAINS |= _team["partner_domains"]

MANAGER_EMAILS = {
    "domenica.galarza@factorial.co",
    "oriol.delmoral@factorial.co",
    "alex.martinez@factorial.co",
    "guillem.catalan@factorial.co",
    "albert.fernandez@factorial.co",
    "samuel.fernandez@factorial.co",
}

ALL_TARGET_EMAILS = ALL_REP_EMAILS | MANAGER_EMAILS


def get_subteam(email: str) -> str | None:
    for name, team in TEAMS.items():
        if email in team["pbd"] or email in team["pae"]:
            return name
    return None


def get_role(email: str, tags: list[str] | None = None) -> str | None:
    in_pbd = email in ALL_PBD_EMAILS
    in_pae = email in ALL_PAE_EMAILS
    if in_pbd and not in_pae:
        return "PBD"
    if in_pae and not in_pbd:
        return "PAE"
    if in_pbd and in_pae:
        if tags and any(t in PAE_TAGS for t in tags):
            return "PAE"
        return "PBD"
    return None


# ── Tags ─────────────────────────────────────────────────────────────────────

PBD_TAGS = {
    "91. Partners - PBD Demo Scheduled",
    "92. Partners - PBD Positive Champion Connected Call",
    "93. Partners - PBD Gatekeeper Call Connected",
    "94. Partners - PBD Connected Call - Objection",
    "991. Partners - PBD Partner Call",
    "95. Partners - PBD Connected Call - Busy/Bad Time",
    "96. Partners - PBD Non Connected - Left Voicemail",
    "97. Partners - PBD Non Connected - No Answer/Busy",
    "98. Partners - PBD Connected Call - Wrong Number",
    "99. Partners - PBD Connected Call - Wrong Champion/Person inside the Company",
    "Partners - PBD Demo Scheduled Call",
}

PAE_TAGS = {
    "Partners - PAE Demo",
    "Partners - PAE Follow Up",
    "Partners - PAE Follow Up Meeting",
    "Partners - PAE Closing Call",
    "Partners - PAE Closing Meeting",
}

ALL_KNOWN_TAGS = PBD_TAGS | PAE_TAGS

TAG_AUDIT_LEVEL = {
    "91. Partners - PBD Demo Scheduled":                                            "full_pbd",
    "92. Partners - PBD Positive Champion Connected Call":                           "full_pbd",
    "94. Partners - PBD Connected Call - Objection":                                 "full_pbd",
    "Partners - PBD Demo Scheduled Call":                                            "full_pbd",
    "93. Partners - PBD Gatekeeper Call Connected":                                  "light",
    "991. Partners - PBD Partner Call":                                              "light",
    "95. Partners - PBD Connected Call - Busy/Bad Time":                             "light",
    "96. Partners - PBD Non Connected - Left Voicemail":                             "light",
    "97. Partners - PBD Non Connected - No Answer/Busy":                             "light",
    "98. Partners - PBD Connected Call - Wrong Number":                              "light",
    "99. Partners - PBD Connected Call - Wrong Champion/Person inside the Company":  "light",
    "Partners - PAE Demo":                                                           "full_pae",
    "Partners - PAE Follow Up":                                                      "light_pae",
    "Partners - PAE Follow Up Meeting":                                              "light_pae",
    "Partners - PAE Closing Call":                                                   "light_pae",
    "Partners - PAE Closing Meeting":                                                "light_pae",
}

HANDOVER_TRIGGER_TAG = "91. Partners - PBD Demo Scheduled"

PAE_CHANNELS = {
    "Alejandro Soto Velasco": "C0B36Q1EX9T",
    "Carlos Sanchez": "C0B33QJLF8B",
    "David Clemente": "C0B33QDE4KD",
    "Jose Donis": "C0B24A51PNE",
    "Joan Lorenzo Galles": "C0B2UMVT5NK",
    "Beatriz Bravo": "C0B8BKTS1CL",
    "Nerea Urien Meizoso": "C0B2UMRUV2T",
    "Pol Bartolomé": "C0B33Q2T7FV",
    "Roberto Morán": "C0B36RD537X",
    "Xavier Fortuny": "C0B1CNJTPMZ",
}

TEAM_LEAD_CHANNELS = {
    "Santander": "C0B36RD537X",   # Roberto Morán
    "Telefónica": "C0B33QJLF8B",  # Carlos Sanchez
}
