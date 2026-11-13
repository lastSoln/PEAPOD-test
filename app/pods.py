"""Example pods and the random-pod generator for the bench."""

import random

NAMES = ["Ana", "Ben", "Chloe", "Dev", "Elif", "Farid", "Grace", "Hiro", "Isha", "Jun",
         "Kai", "Lena", "Mara", "Nico", "Omar", "Priya", "Quinn", "Ravi", "Sofia", "Theo"]


def _m(name, interests, favourites, tier, travel, style, zone, over18=True, needs=""):
    return {"name": name, "interests": interests, "favourites": favourites, "budget_tier": tier,
            "travel": travel, "style": style, "over18": over18, "home": {"zone": zone}, "needs": needs}


EXAMPLE_PODS = [
    {"name": "The Weekend Crew (mixed tastes)", "members": [
        _m("Mara", ["cafe", "sights", "eat"], ["Specialty coffee", "Art galleries"], "mid", "town", "explorer", "Central"),
        _m("Jun", ["active", "eat", "play"], ["Hiking", "Local & street food"], "low", "far", "foodie", "East"),
        _m("Theo", ["bars", "sights", "cafe", "play"], ["Cocktail bars", "Museums", "Karaoke"], "high", "town", "planner", "West"),
        _m("Kai", ["nature", "shop", "cafe"], [], "mid", "town", "flow", "North-East"),
    ]},
    {"name": "Family with a teenager (one under 18)", "members": [
        _m("Mum", ["nature", "cafe", "sights"], ["Gardens & parks", "Bakeries & pastries"], "mid", "town", "planner", "North"),
        _m("Dad", ["eat", "active", "sights"], ["Local & street food", "Cycling"], "mid", "town", "flow", "North"),
        _m("Isha", ["play", "cafe", "zoo", "shows"], ["Arcades & VR", "Tea & boba", "Cinema"], "low", "town", "explorer", "North", over18=False),
    ]},
    {"name": "Foodies (everyone picks food)", "members": [
        _m("Ravi", ["eat", "cafe", "bars"], ["Asian", "Grill, hotpot & BBQ"], "mid", "town", "foodie", "Central"),
        _m("Sofia", ["eat", "cafe", "shop"], ["Western & European", "Brunch", "Desserts & ice cream"], "high", "far", "foodie", "South"),
        _m("Omar", ["eat", "cafe", "sights"], ["Middle Eastern & Mediterranean", "Specialty coffee"], "mid", "town", "foodie", "East"),
        _m("Lena", ["eat", "cafe", "bars"], ["Local & street food", "Wine & craft beer"], "mid", "town", "explorer", "Central"),
        _m("Hiro", ["eat", "cafe", "play"], ["Asian", "Tea & boba"], "high", "far", "planner", "West"),
    ]},
    {"name": "Tight budget, spread across the island", "members": [
        _m("Ana", ["nature", "eat", "shop"], ["Easy nature walks", "Markets & flea markets"], "low", "far", "flow", "West"),
        _m("Ben", ["nature", "cafe", "shop"], ["Beaches, lakes & islands", "Vintage & thrift"], "low", "far", "explorer", "East"),
        _m("Dev", ["nature", "eat", "shop"], ["Gardens & parks", "Bookshops"], "low", "far", "flow", "North"),
        _m("Elif", ["nature", "cafe", "sights"], ["Viewpoints & sunsets", "Art galleries"], "mid", "far", "explorer", "South"),
        _m("Nico", ["active", "cafe", "shop"], ["Hiking", "Tea & boba"], "low", "town", "flow", "North-East"),
        _m("Priya", ["spa", "cafe", "sights"], ["Yoga & pilates", "Museums"], "low", "far", "planner", "Central"),
    ]},
    {"name": "Homebodies (everyone stays close by)", "members": [
        _m("Chloe", ["cafe", "shop", "sights"], ["Specialty coffee", "Bookshops"], "mid", "close", "flow", "Central"),
        _m("Farid", ["eat", "play", "shows"], ["Asian", "Cinema"], "mid", "close", "flow", "Central"),
        _m("Grace", ["nature", "cafe", "spa"], ["Gardens & parks"], "mid", "close", "planner", "South"),
    ]},
    {"name": "Night owls (all over 18)", "members": [
        _m("Quinn", ["bars", "play", "eat"], ["Cocktail bars", "Karaoke", "Clubs & dancing"], "high", "far", "explorer", "Central"),
        _m("Farid", ["bars", "shows", "eat"], ["Wine & craft beer", "Concerts & gigs", "Grill, hotpot & BBQ"], "mid", "town", "foodie", "South"),
        _m("Grace", ["bars", "shows", "eat"], ["Cocktail bars", "Theatre & musicals"], "high", "town", "planner", "Central"),
    ]},
]


def random_pod(tiles, zones, tiers, seed=None):
    """3 to 10 members, each with 3 to 5 interest tiles and 0 to 3 favourites inside them."""
    rng = random.Random(seed)
    names = rng.sample(NAMES, rng.randint(3, 10))
    usable = [t for t in tiles if t["chips"]]
    members = []
    for name in names:
        picked = rng.sample(usable, rng.randint(3, 5))
        favourites = []
        for t in picked:
            if rng.random() < 0.6:
                favourites.extend(c["name"] for c in rng.sample(t["chips"], min(len(t["chips"]), rng.randint(1, 2))))
        members.append({
            "name": name, "interests": [t["key"] for t in picked], "favourites": favourites[:6],
            "budget_tier": rng.choices([t["key"] for t in tiers], [3, 4, 2][:len(tiers)] or None)[0],
            "travel": rng.choices(["close", "town", "far"], [2, 5, 3])[0],
            "style": rng.choice(["flow", "planner", "explorer", "foodie"]),
            "over18": rng.random() < 0.85,
            "home": {"zone": rng.choice(zones)}, "needs": "",
        })
    return {"name": f"Random pod (seed {seed})", "members": members}
