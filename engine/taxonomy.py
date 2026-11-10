"""Peapod taxonomy: zones, hubs and interest tiles.

Tiles come from the alpha onboarding design (Q1 Interests). A tile groups
chips; "same tile" is what the taste score means by a near match. Chips that
are in the design but not in the dataset are kept here so the mapping stays
complete, but the bench only offers chips that exist in the dataset.
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
