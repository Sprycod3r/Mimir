"""
kb_scaffold.py — Mimir Knowledge Base Folder Scaffold

Creates the full hierarchical folder structure under knowledge/.
Run once during first setup. Safe to re-run — never overwrites existing files.

Each folder gets a _README.md that describes what belongs there.
All content files the user adds should follow the .md frontmatter format.
"""

from pathlib import Path


# Full scaffold definition: {relative_path: description_for_readme}
KB_STRUCTURE = {
    "survival-independence": "Practical skills for self-reliance — water, food, fire, shelter, navigation, grid-down scenarios.",
    "survival-independence/water": "Water sourcing, purification, and storage.",
    "survival-independence/water/purification": "Filtration, chemical treatment, boiling, UV methods.",
    "survival-independence/water/collection-rainwater": "Rainwater harvesting systems and legal considerations.",
    "survival-independence/water/well-hand-pump": "Hand-pump installation, maintenance, and repair.",
    "survival-independence/food-storage": "Long-term food storage systems and rotation.",
    "survival-independence/food-storage/long-term": "Dry goods, freeze-dried, MREs — storage duration and rotation.",
    "survival-independence/food-storage/canning-preservation": "Water bath and pressure canning, fermentation, dehydration.",
    "survival-independence/food-storage/rotation-systems": "FIFO, inventory tracking, shelf life reference.",
    "survival-independence/fire": "Fire starting methods and safety.",
    "survival-independence/fire/starting-methods": "Friction, ferro rod, lighter, magnifying glass — tools and techniques.",
    "survival-independence/fire/fire-safety": "Safe fire building, extinguishing, wildfire awareness.",
    "survival-independence/shelter": "Emergency shelter building and off-grid structures.",
    "survival-independence/shelter/emergency": "Tarps, debris huts, snow shelters, vehicle shelter.",
    "survival-independence/shelter/off-grid-structures": "Cabins, earthbag, cordwood, and other permanent off-grid builds.",
    "survival-independence/navigation": "Land navigation and wayfinding without electronics.",
    "survival-independence/navigation/land-nav": "Map and compass, terrain association, pace count.",
    "survival-independence/navigation/maps-compass": "Topographic map reading, compass types, declination.",
    "survival-independence/security": "Property and personal security.",
    "survival-independence/security/property": "Perimeter security, lighting, access control, dogs.",
    "survival-independence/security/personal": "Situational awareness, personal defense, de-escalation.",
    "survival-independence/grid-down": "Scenarios and systems for operating without utility infrastructure.",
    "survival-independence/grid-down/power-generation": "Solar, generator, battery bank — sizing, wiring, and maintenance.",
    "survival-independence/grid-down/communications": "Ham radio, GMRS, mesh networks, signal protocol.",

    "health-medicine": "Medical reference, first aid, medications, and long-term care.",
    "health-medicine/first-aid": "Immediate trauma and injury response.",
    "health-medicine/first-aid/trauma": "Bleeding control, tourniquets, wound packing, shock management.",
    "health-medicine/first-aid/burns": "Burn classification, treatment, and dressing.",
    "health-medicine/first-aid/fractures": "Splinting, immobilization, field assessment.",
    "health-medicine/medications": "Medication storage, dosing, and interactions reference.",
    "health-medicine/medications/storage": "Temperature, humidity, shelf life, and rotation.",
    "health-medicine/medications/dosing-reference": "Adult and pediatric dosing tables for common medications.",
    "health-medicine/medications/interactions": "Common drug interaction reference.",
    "health-medicine/pediatric": "Child health — general and specialist reference.",
    "health-medicine/pediatric/general": "Pediatric first aid, fever management, common illnesses.",
    "health-medicine/pediatric/endocrinology": "Congenital Adrenal Hyperplasia (CAH) management, adrenal crisis protocol, specialist reference.",
    "health-medicine/dental": "Dental first aid, infection management, pain relief.",
    "health-medicine/mental-health": "Stress, anxiety, ADHD management strategies, crisis resources.",
    "health-medicine/nutrition": "Macronutrients, micronutrients, caloric needs, special diets.",
    "health-medicine/long-term-care": "Managing chronic conditions, wound care, care protocols.",

    "homestead-land": "Gardening, livestock, water systems, and land management.",
    "homestead-land/soil-garden": "Soil health, garden planning, and pest management.",
    "homestead-land/soil-garden/planting-guides": "Planting calendars, companion planting, spacing.",
    "homestead-land/soil-garden/composting": "Hot and cold composting, vermicomposting, inputs.",
    "homestead-land/livestock": "Animal husbandry reference.",
    "homestead-land/livestock/chickens": "Breeds, housing, feeding, egg production, health.",
    "homestead-land/livestock/goats": "Breeds, housing, milking, feeding, health.",
    "homestead-land/livestock/general-husbandry": "Herd management, biosecurity, record keeping.",
    "homestead-land/water-systems": "Irrigation and water storage.",
    "homestead-land/water-systems/irrigation": "Drip, flood, sprinkler — design and maintenance.",
    "homestead-land/water-systems/cisterns": "Sizing, materials, placement, filtration.",
    "homestead-land/fencing": "Types, materials, installation, electric fence.",
    "homestead-land/land-management": "Erosion control, timber management, pasture rotation.",
    "homestead-land/food-production": "Integrated food production systems and seasonal planning.",

    "building-repair": "Construction, repair, and home systems.",
    "building-repair/foundations": "Types, drainage, waterproofing, crack repair.",
    "building-repair/framing": "Platform, post-and-beam, timber framing basics.",
    "building-repair/roofing": "Materials, installation, repair, flashing.",
    "building-repair/plumbing": "Supply, drain, water heaters, well systems.",
    "building-repair/electrical": "Residential and off-grid electrical.",
    "building-repair/electrical/residential": "Circuits, panels, outlets, code basics.",
    "building-repair/electrical/solar-off-grid": "Solar panel sizing, charge controllers, inverters, battery banks.",
    "building-repair/hvac": "Heating, cooling, ventilation — system types and maintenance.",
    "building-repair/finishing": "Drywall, flooring, painting, trim.",
    "building-repair/tools-equipment": "Tool selection, use, and maintenance.",

    "vehicles": "Vehicle maintenance, repair, and off-road operation.",
    "vehicles/maintenance": "Scheduled maintenance by vehicle type.",
    "vehicles/maintenance/diesel": "Diesel-specific maintenance — fuel filters, glow plugs, injectors.",
    "vehicles/maintenance/gas": "Gas engine maintenance — oil, filters, spark plugs, belts.",
    "vehicles/repair": "Common repair procedures.",
    "vehicles/repair/engine": "Diagnostics, top-end, bottom-end procedures.",
    "vehicles/repair/transmission": "Manual and automatic — common issues and repair.",
    "vehicles/repair/brakes": "Pads, rotors, calipers, lines, bleeding.",
    "vehicles/off-road": "4WD operation, recovery gear, winching, tire airing.",
    "vehicles/emergency-field-repair": "Roadside and remote repairs — what you can do with limited tools.",

    "technology": "IT, cybersecurity, networking, and hardware.",
    "technology/networking": "Network infrastructure and home lab.",
    "technology/networking/home-lab": "Switch/router setup, VLANs, pfSense, monitoring.",
    "technology/networking/infrastructure": "Enterprise concepts — subnetting, DNS, DHCP, VPN.",
    "technology/cybersecurity": "Security concepts, tools, and certifications.",
    "technology/cybersecurity/fundamentals": "CIA triad, threat models, common attack types.",
    "technology/cybersecurity/tools": "Nmap, Wireshark, Nessus, Metasploit, and others.",
    "technology/cybersecurity/certifications": "Security+, CySA+, CCNA — exam notes and resources.",
    "technology/linux": "Linux administration, scripting, and common distros.",
    "technology/windows-admin": "Active Directory, Group Policy, PowerShell, imaging.",
    "technology/hardware": "PC building, components, troubleshooting, server hardware.",
    "technology/3d-printing": "3D printing techniques and materials.",
    "technology/3d-printing/slicing": "Slicer settings, supports, infill, print profiles.",
    "technology/3d-printing/materials": "PLA, PETG, ABS, TPU, PA6-CF — properties and use cases.",
    "technology/radio-comms": "Amateur and GMRS radio.",
    "technology/radio-comms/ham": "Ham radio licensing, operating procedures, equipment.",
    "technology/radio-comms/gmrs": "GMRS licensing, repeaters, equipment selection.",

    "crafting-fabrication": "Making things — metal, wood, leather, costuming.",
    "crafting-fabrication/metalworking": "Cutting, grinding, forming — tools and techniques.",
    "crafting-fabrication/woodworking": "Hand tools, power tools, joinery, finishing.",
    "crafting-fabrication/welding": "MIG, TIG, stick — techniques, safety, metal prep.",
    "crafting-fabrication/leatherwork": "Tools, stitching, finishing, patterns.",
    "crafting-fabrication/costuming-armor": "Sci-fi and fantasy costume fabrication.",
    "crafting-fabrication/costuming-armor/3d-printed-props": "Design, print settings, and assembly for wearable props.",
    "crafting-fabrication/costuming-armor/electronics-integration": "Fans, LEDs, voice modulation, control panels — wiring and integration.",
    "crafting-fabrication/costuming-armor/materials-finishing": "EVA foam, Worbla, resin, paint, weathering.",
    "crafting-fabrication/general-fabrication": "Cross-discipline fabrication techniques and material sourcing.",

    "legal-financial": "Law, finance, and veteran-specific benefits.",
    "legal-financial/general-law": "Property, contracts, and family law reference.",
    "legal-financial/general-law/property-rights": "Easements, mineral rights, water rights, zoning.",
    "legal-financial/general-law/contracts": "Reading and understanding contracts — key clauses.",
    "legal-financial/general-law/family-law": "Custody, co-parenting, court orders.",
    "legal-financial/personal-finance": "Investing, budgeting, and taxes.",
    "legal-financial/personal-finance/investing": "Index funds, TSP, Roth IRA, brokerage accounts.",
    "legal-financial/personal-finance/budgeting": "Zero-based budgeting, expense tracking, emergency fund.",
    "legal-financial/personal-finance/taxes": "Federal and state tax basics, deductions, filing.",
    "legal-financial/veteran-benefits": "VA benefits, disability ratings, education benefits, property tax exemptions.",
    "legal-financial/estate-planning": "Wills, POA, trusts, beneficiary designations.",
    "legal-financial/land-purchase": "Due diligence checklist, title, surveys, well/septic inspection.",

    "reference": "Math, science, and general reference.",
    "reference/math": "Mathematics reference.",
    "reference/math/algebra": "Equations, functions, and formulas.",
    "reference/math/geometry": "Area, volume, angles, and trigonometry.",
    "reference/math/statistics": "Probability, distributions, basic statistical analysis.",
    "reference/science": "Physical and life sciences.",
    "reference/science/physics": "Mechanics, thermodynamics, electricity and magnetism.",
    "reference/science/chemistry": "Elements, reactions, acids/bases, safety.",
    "reference/science/biology": "Cells, genetics, anatomy, ecology basics.",
    "reference/earth-science": "Geology and meteorology.",
    "reference/earth-science/geology": "Rock types, soil formation, topography.",
    "reference/earth-science/meteorology": "Weather patterns, storm identification, forecasting basics.",
    "reference/history": "Historical reference and context.",
    "reference/general-reference": "Conversion tables, constants, and miscellaneous reference.",

    "personal-vault": "Private documents, SOPs, contacts, and notes.",
    "personal-vault/sops": "Personal standard operating procedures for recurring tasks.",
    "personal-vault/contacts": "Important contacts and reference numbers.",
    "personal-vault/documents": "Personal document copies and summaries.",
    "personal-vault/notes": "Freeform notes and working documents.",

    "entertainment": "Gaming lore, creative projects, and media notes.",
    "entertainment/gaming": "Game-specific notes and guides.",
    "entertainment/gaming/tarkov": "Escape from Tarkov — lore, maps, mechanics, loadouts.",
    "entertainment/gaming/general": "Other game notes.",
    "entertainment/creative-writing": "Original creative writing projects.",
    "entertainment/creative-writing/shadow-goons": "Shadow Goons saga — characters, timeline, world-building.",
    "entertainment/creative-writing/general": "Other creative writing notes.",
    "entertainment/cosplay-projects": "Cosplay and prop build notes.",
    "entertainment/cosplay-projects/ct-1129-vigil": "CT-1129 Vigil build — components, progress, reference.",
    "entertainment/cosplay-projects/general": "Other cosplay build notes.",
    "entertainment/media-notes": "Reviews, recommendations, and watchlist notes.",
}


README_TEMPLATE = """\
---
title: {title}
domain: {domain}
subdomain: {subdomain}
tags:
source: original
last_updated:
---

# {title}

{description}

## How to add content here

Create `.md` files in this folder with the following frontmatter header:

```yaml
---
title: Your Document Title
domain: {domain}
subdomain: {subdomain}
tags: tag1, tag2, tag3
source: where this came from (book, website, personal experience)
last_updated: YYYY-MM-DD
---
```

Then write your content in Markdown below the frontmatter.
"""

FRONTMATTER_TEMPLATE = """\
---
title:
domain:
subdomain:
tags:
source:
last_updated:
---

"""


def scaffold_knowledge_base(knowledge_dir: Path, verbose: bool = False) -> int:
    """
    Create the full knowledge base folder structure.
    Adds a _README.md to each folder describing what belongs there.
    Never overwrites existing files.
    Returns the number of new folders created.
    """
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    created = 0

    for rel_path, description in KB_STRUCTURE.items():
        folder = knowledge_dir / rel_path
        folder.mkdir(parents=True, exist_ok=True)

        readme_path = folder / "_README.md"
        if not readme_path.exists():
            parts = rel_path.split("/")
            domain = parts[0]
            subdomain = parts[-1] if len(parts) > 1 else parts[0]
            title = subdomain.replace("-", " ").title()

            content = README_TEMPLATE.format(
                title=title,
                domain=domain,
                subdomain=subdomain,
                description=description,
            )
            readme_path.write_text(content, encoding="utf-8")
            created += 1
            if verbose:
                print(f"  Created: {rel_path}/_README.md")

    return created


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python kb_scaffold.py <path_to_knowledge_dir>")
        sys.exit(1)

    target = Path(sys.argv[1])
    print(f"Scaffolding knowledge base at: {target}")
    n = scaffold_knowledge_base(target, verbose=True)
    print(f"\nDone. {n} README files created.")
