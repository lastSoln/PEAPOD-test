"""Peapod taxonomy: zones, hubs, interest tiles and the onboarding answers.

Everything here mirrors the alpha app design: Q1 interests (tiles and their
favourites), Q2 spend, Q3 travel time, Q4 plan style, and the vote reasons on
the plan page. Chips that are in the design but not in the dataset are kept so
the mapping stays complete; the bench only offers chips that have places.
"""

ZONES = ["Central", "North", "North-East", "East", "South", "West"]

HUBS = [
    "Food",
    "Cafes, sweets and soft drinks",
    "Bars and nightlife",
    "Outdoors and active",
    "Culture and shows",
    "Play and attractions",
    "Wellness",
    "Make and browse",
]

ADULT_HUB = "Bars and nightlife"
FOOD_HUBS = {"Food", "Cafes, sweets and soft drinks"}
CHILL_HUBS = {"Cafes, sweets and soft drinks", "Wellness", "Culture and shows", "Make and browse"}
ACTIVE_HUBS = {"Outdoors and active", "Play and attractions"}

TILES = [
    {"key": "eat", "label": "Eat Out", "chips": [
        "Local & street food", "Asian", "Western & European",
        "Middle Eastern & Mediterranean", "Grill, hotpot & BBQ", "Fine dining & tasting menus"]},
    {"key": "cafe", "label": "Cafés & Sweet Treats", "chips": [
        "Specialty coffee", "Brunch", "Desserts & ice cream", "Bakeries & pastries", "Tea & boba"]},
    {"key": "zoo", "label": "Zoos, Aquariums & Theme Parks", "chips": [
        "Zoos & wildlife parks", "Aquariums", "Theme parks & rides", "Water parks", "Farms & petting zoos"]},
    {"key": "classes", "label": "Classes & Workshops", "chips": [
        "Cooking & baking", "Pottery & ceramics", "Art jams & painting", "Dance", "Crafts", "Drinks-making"]},
    {"key": "nature", "label": "Nature & Parks", "chips": [
        "Gardens & parks", "Easy nature walks", "Beaches, lakes & islands", "Viewpoints & sunsets", "Picnic spots"]},
    {"key": "spa", "label": "Spas & Wellness", "chips": [
        "Massage & spa treatments", "Sauna, bathhouses & hot springs", "Yoga & pilates", "Pool & beach-club days"]},
    {"key": "active", "label": "Active & Sports", "chips": [
        "Hiking", "Cycling", "Climbing & bouldering", "Water sports", "Racket sports", "Snow & ice sports"]},
    {"key": "bars", "label": "Bars & Nightlife", "chips": [
        "Cocktail bars", "Wine & craft beer", "Rooftop bars", "Live-music bars", "Clubs & dancing"]},
    {"key": "shows", "label": "Shows & Live Events", "chips": [
        "Concerts & gigs", "Theatre & musicals", "Comedy", "Cinema", "Festivals & fairs", "Sports matches"]},
    {"key": "play", "label": "Games & Play", "chips": [
        "Escape rooms", "Karaoke", "Arcades & VR", "Board-game cafés", "Bowling, mini golf & karting"]},
    {"key": "shop", "label": "Shopping & Markets", "chips": [
        "Markets & flea markets", "Vintage & thrift", "Bookshops", "Design & concept stores", "Malls & outlets"]},
    {"key": "sights", "label": "Sights & Culture", "chips": [
        "Museums", "Art galleries", "Historic & old-town walks", "Landmarks & architecture", "Guided tours"]},
]

CHIP_TILE = {chip: tile["key"] for tile in TILES for chip in tile["chips"]}
TILE_CHIPS = {tile["key"]: list(tile["chips"]) for tile in TILES}
TILE_LABEL = {tile["key"]: tile["label"] for tile in TILES}

# Q3 "How far do you usually go?" The minutes are tunable weights; "far" has no limit.
TRAVEL_PREFS = [
    {"key": "close", "label": "Close by", "sub": "About 15 minutes"},
    {"key": "town", "label": "Across town", "sub": "30 to 45 minutes"},
    {"key": "far", "label": "Out of town", "sub": "An hour or more"},
]

# Q4 "Who are you when you make plans?"
STYLES = [
    {"key": "flow", "label": "Go with the flow", "does": "Keeps it easy: fewer stops, more time at each."},
    {"key": "planner", "label": "The Planner", "does": "The full day, minute by minute."},
    {"key": "explorer", "label": "The Explorer", "does": "Somewhere new every time."},
    {"key": "foodie", "label": "The Foodie", "does": "Every plan built around the best bites."},
]

# Vote reasons. Practical ones rework this plan only; "not for me" ones put the member out
# and nudge their taste.
PRACTICAL_REASONS = [
    {"key": "too_far", "label": "Too far"},
    {"key": "too_pricey", "label": "Too pricey"},
    {"key": "wrong_time", "label": "Wrong time"},
    {"key": "busy_that_day", "label": "Busy that day"},
]
NOT_FOR_ME_REASONS = [
    {"key": "not_my_thing", "label": "Not my thing anymore"},
    {"key": "not_with_group", "label": "Not with this group"},
    {"key": "done_lately", "label": "Done it lately"},
]
PRACTICAL = {r["key"] for r in PRACTICAL_REASONS}
NOT_FOR_ME = {r["key"] for r in NOT_FOR_ME_REASONS}
