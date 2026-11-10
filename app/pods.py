"""Example pods and the random-pod generator for the bench."""

import random

NAMES = ["Ana", "Ben", "Chloe", "Dev", "Elif", "Farid", "Grace", "Hiro", "Isha", "Jun",
         "Kai", "Lena", "Mara", "Nico", "Omar", "Priya", "Quinn", "Ravi", "Sofia", "Theo"]


def _m(name, chips, tier, over18, zone, needs=""):
    return {"name": name, "chips": chips, "budget_tier": tier, "over18": over18,
            "home": {"zone": zone}, "needs": needs}


EXAMPLE_PODS = [
    {"name": "The Weekend Crew (mixed tastes)", "members": [
        _m("Mara", ["Specialty coffee", "Art galleries", "Asian"], "mid", True, "Central"),
        _m("Jun", ["Hiking", "Local & street food", "Arcades & VR"], "low", True, "East"),
        _m("Theo", ["Cocktail bars", "Museums", "Desserts & ice cream", "Karaoke"], "high", True, "West"),
        _m("Kai", ["Gardens & parks", "Bookshops", "Tea & boba"], "mid", True, "North-East"),
    ]},
    {"name": "Family with a teenager (one under 18)", "members": [
        _m("Mum", ["Gardens & parks", "Bakeries & pastries", "Museums"], "mid", True, "North"),
        _m("Dad", ["Local & street food", "Cycling", "Landmarks & architecture"], "mid", True, "North"),
        _m("Isha", ["Arcades & VR", "Tea & boba", "Theme parks & rides", "Cinema"], "low", False, "North"),
    ]},
    {"name": "Foodies (everyone picks food)", "members": [
        _m("Ravi", ["Asian", "Grill, hotpot & BBQ", "Local & street food"], "mid", True, "Central"),
        _m("Sofia", ["Western & European", "Brunch", "Desserts & ice cream"], "high", True, "South"),
        _m("Omar", ["Middle Eastern & Mediterranean", "Asian", "Specialty coffee"], "mid", True, "East"),
        _m("Lena", ["Local & street food", "Bakeries & pastries", "Wine & craft beer"], "mid", True, "Central"),
        _m("Hiro", ["Asian", "Tea & boba", "Grill, hotpot & BBQ"], "high", True, "West"),
    ]},
    {"name": "Tight budget, spread across the island", "members": [
        _m("Ana", ["Easy nature walks", "Local & street food", "Markets & flea markets"], "low", True, "West"),
        _m("Ben", ["Beaches, lakes & islands", "Specialty coffee", "Vintage & thrift"], "low", True, "East"),
        _m("Dev", ["Gardens & parks", "Asian", "Bookshops"], "low", True, "North"),
        _m("Elif", ["Viewpoints & sunsets", "Desserts & ice cream", "Art galleries"], "mid", True, "South"),
        _m("Nico", ["Hiking", "Tea & boba", "Malls & outlets"], "low", True, "North-East"),
        _m("Priya", ["Yoga & pilates", "Bakeries & pastries", "Museums"], "low", True, "Central"),
    ]},
    {"name": "Night owls (all over 18)", "members": [
        _m("Quinn", ["Cocktail bars", "Karaoke", "Clubs & dancing"], "high", True, "Central"),
        _m("Farid", ["Wine & craft beer", "Concerts & gigs", "Grill, hotpot & BBQ"], "mid", True, "South"),
        _m("Grace", ["Cocktail bars", "Theatre & musicals", "Western & European"], "high", True, "Central"),
    ]},
]


def random_pod(chips, zones, tiers, seed=None):
    """3 to 10 members with 3 to 5 chips each. Chips are weighted towards common ones."""
    rng = random.Random(seed)
    names = rng.sample(NAMES, rng.randint(3, 10))
    chip_names = [c for c, _ in chips]
    weights = [n ** 0.35 for _, n in chips]     # flatten so rare chips still turn up
    members = []
    for name in names:
        picks, want = [], rng.randint(3, 5)
        while len(picks) < want:
            c = rng.choices(chip_names, weights)[0]
            if c not in picks:
                picks.append(c)
        members.append({
            "name": name, "chips": picks,
            "budget_tier": rng.choices([t["key"] for t in tiers], [3, 4, 2][:len(tiers)] or None)[0],
            "over18": rng.random() < 0.85,
            "home": {"zone": rng.choice(zones)}, "needs": "",
        })
    return {"name": f"Random pod (seed {seed})", "members": members}
