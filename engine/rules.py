"""Every rule the engine applies, in one place, so the team can read and argue with them.

Each rule has an id, the stage it belongs to, what it does in plain words, where it
comes from, and the weight or setting that tunes it (if any).

source:
  "manual"  from the Peapod Engine Manual / "How a Peapod Plan Works"
  "design"  from the alpha app design (onboarding answers, plan rule book v64, user flow v64)
  "guess"   my own choice where neither says; the first things to question
"""

RULES = [
    # ---- Gather
    ("G1", "Gather", "Freeze a snapshot when the plan is requested: who is going, each person's limits, interests, favourites, plan style, learned taste and home, plus the request. Later rounds reuse it.", "manual", None),
    ("G2", "Gather", "The pitcher is in from the start and never swipes. A Peapod pick has no pitcher, so everyone swipes.", "design", None),
    ("G3", "Gather", "Anyone who is out (Can't, 3 missed rounds, or left) no longer shapes the plan: their limits and taste are dropped at the next rework or edit.", "guess", None),

    # ---- Filter (hard limits)
    ("F1", "Filter", "Only places with status = active.", "manual", None),
    ("F2", "Filter", "A fixed Area row means that zone only.", "manual", None),
    ("F3", "Filter", "Bars and nightlife only if every member going ticked over 18.", "manual", None),
    ("F4", "Filter", "Budget: the lowest spend tier among the people going. A fixed Budget row can lower it, never raise it. The plan's total estimated cost (midpoint of each place's price range) must fit under that tier's upper limit.", "manual", "budget tiers"),
    ("F5", "Filter", "Distance: every stop must be reachable from each member's home within their travel answer, by the fastest of walking, public transport, car or cab. Close by = 15 min, Across town = 45 min, Out of town = no limit.", "design + guess", "travel_close_min, travel_town_min"),
    ("F6", "Filter", "Region: a member's home is their saved zone (its centre) or exact coordinates. It anchors rule F5 and the leave-home times. A member with no home has no distance limit.", "design + guess", None),
    ("F7", "Filter", "A place a going member said they had 'Done lately' or would do 'Not with this group' is left out.", "design", None),
    ("F8", "Filter", "Open for the whole visit at the real arrival time, using the typical (mostly estimated) hours. A weekday with no hours is closed. Sessions can run past midnight.", "manual", None),
    ("F9", "Filter", "A kind (hub) with fewer than 3 eligible places is empty. If the Kind row needs it, the engine fails and names the row.", "manual", "min_hub_places"),
    ("F10", "Filter", "Hard limits are never loosened to make a plan fit. Diet, allergies, ratings, accessibility and 'needs' are ignored. Unanswered counts as none.", "manual", None),

    # ---- Taste (ranking)
    ("T1", "Taste", "A member picks 3 to 5 interest tiles, and optionally favourites (chips) inside them. A favourite is an exact match. Another chip from a picked tile is a same-interest match. A tile picked with no favourites counts every chip in it as exact.", "design + guess", "chip_exact, chip_same_tile"),
    ("T2", "Taste", "Majority first: rank by the share of counted members who match, then by the sum of their match scores.", "manual", "majority_share"),
    ("T3", "Taste", "A member with no pick for that kind of stop is not counted, so they do not pull the share down.", "manual", None),
    ("T4", "Taste", "Fairness: a stop gets a bonus scaled by the share of still-unmatched members it would serve, so each member gets at least one stop from their own picks where possible.", "manual", "fairness_bonus"),
    ("T5", "Taste", "Places with no chip are matched by kind only and get a flat, lower score.", "manual", "no_chip_base"),
    ("T6", "Taste", "Price closeness: a small bonus for a price near the per-stop target for the pod's lowest budget.", "manual", "price_closeness"),
    ("T7", "Taste", "Learned taste multiplies a member's match on specific chips: down after 'Not my thing anymore', up after a heart.", "design", "taste_down, taste_heart"),

    # ---- Plan style (soft)
    ("S1", "Plan style", "Go with the flow: a bonus for stops close to the last one, scaled by the share of easygoing members. If they are the majority, the day has one stop fewer and each visit is 25% longer.", "design + guess", "style_flow, flow_visit_factor"),
    ("S2", "Plan style", "The Planner: a bonus for places whose hours are confirmed rather than estimated, scaled by the share of planners. If they are the majority, the day has one stop more.", "design + guess", "style_planner"),
    ("S3", "Plan style", "The Explorer: a bonus for one-off places (not a chain) and for chips nobody picked, scaled by the share of explorers.", "design + guess", "style_explorer"),
    ("S4", "Plan style", "The Foodie: a bonus for food and cafe stops, scaled by the share of foodies. With any foodie in the pod, a Day out counts Food as a kind the pod wants.", "design + guess", "style_foodie"),
    ("S5", "Plan style", "Plan style never filters a place out. It only moves the ranking.", "manual", None),

    # ---- Walk
    ("W1", "Walk", "A Moment is one stop. A Day out is 3 to 5 stops, chosen one at a time.", "manual", "n_stops"),
    ("W2", "Walk", "Each next stop must be a kind the pod still wants and has not had yet. If nothing fits, the kind mix is loosened: any wanted kind except the previous one, then any kind.", "manual", None),
    ("W3", "Walk", "Variety: a penalty when a stop repeats the previous stop's kind.", "manual", "variety_penalty"),
    ("W4", "Walk", "Distance: a penalty per km from the previous stop. The first stop is measured from the middle of the members' homes.", "manual + guess", "distance_penalty_per_km"),
    ("W5", "Walk", "Each leg must be under the max travel time. Up to 1.2 km is a walk at 13 min per km; further is public transport.", "design", "max_travel_minutes"),
    ("W6", "Walk", "One slot, the last stop, is kept for something new: any kind is allowed and a kind or chip nobody picked gets a bonus.", "manual + guess", "new_slot_bonus"),
    ("W7", "Walk", "A fixed Kind row fixes the first stop's kind on a Day out, and the only stop on a Moment.", "guess", None),
    ("W8", "Walk", "Budget reserve: each stop still to come keeps a small reserve (up to $8) so an early stop cannot spend the whole budget.", "guess", None),
    ("W9", "Walk", "No place twice, and no two places with the same name (chains).", "guess", None),
    ("W10", "Walk", "A seeded random tie-break. The same pod, request, weights and seed always give the same plan.", "manual", "seed_jitter"),

    # ---- Assemble
    ("A1", "Assemble", "Each start time = when the stop before ends + the leg between them, rounded up to 5 minutes.", "design", None),
    ("A2", "Assemble", "Every stop gets a one-line reason and 2 to 4 alternatives (the next best candidates, same kind first).", "manual", "alternatives"),
    ("A3", "Assemble", "Each member sees when to leave home for walking, public transport, car and cab: straight-line distance x detour / speed + a fixed overhead. No saved home shows nothing.", "manual", "travel speeds"),
    ("A4", "Assemble", "If nothing fits, say so plainly. Never say whose limit or which limit blocked it.", "manual", None),

    # ---- Swiping
    ("V1", "Swiping", "Everyone who has not said yes swipes: I'm in, Maybe or Can't. A round ends when they have all answered (or after 24 hours).", "design", None),
    ("V2", "Swiping", "I'm in: you are in and stay in. No more swiping, no leaving until it's a plan.", "design", None),
    ("V3", "Swiping", "Maybe, or Can't with a practical reason (Too far, Too pricey, Wrong time, Busy that day): you would go with a change. You stay in the rounds and Peapod reworks the plan around the reason.", "manual + design", None),
    ("V4", "Swiping", "Can't with a 'not for me' reason (Not my thing anymore, Not with this group, Done it lately), or with no reason: you are out. Nothing changes because of you.", "manual + design", None),
    ("V5", "Swiping", "No answer counts as Can't with no reason: nothing changes and you are asked again next round. Three missed rounds in a row puts you out. Any swipe resets the count.", "design", "max_missed"),
    ("V6", "Swiping", "Three rounds at most. Round 3 is final: I'm in or Can't only. Anyone who has not said I'm in by the end is out.", "manual", "max_rounds"),
    ("V7", "Swiping", "The itinerary is locked while swiping. Only Peapod changes it, and only between rounds.", "design", None),
    ("V8", "Swiping", "When everyone left is I'm in and at least 2 are in, it becomes a plan (Planning). With fewer than 2 in, the plan ends and stays ended.", "manual", "min_going"),
    ("V9", "Swiping", "Reasons are private. The pod sees who is in, Maybe or out, never why, and never whose limit ruled a place out.", "manual", None),

    # ---- Rework
    ("R1", "Rework", "Change the smallest thing that answers the reasons. A stop stays unless it breaks a limit the reasons tightened.", "manual", None),
    ("R2", "Rework", "All reasons in a round are applied together, and every hard limit of everyone still going keeps applying, so a rework still works for those already in.", "design", None),
    ("R3", "Rework", "Too far: that member's travel limit for this plan becomes their longest trip to any current stop x 0.75. Stops beyond it are replaced.", "guess", "rework_far_factor"),
    ("R4", "Rework", "Too pricey: this plan's budget becomes its current cost x 0.75. The priciest stops are let go until the rest fits, then replaced with cheaper ones.", "guess", "rework_price_factor"),
    ("R5", "Rework", "Wrong time: the start moves 2 hours later, or 2 hours earlier if later would end after 23:30. Stops closed at the new time are replaced.", "guess", "rework_time_shift_min"),
    ("R6", "Rework", "Busy that day: a Saturday plan moves to Sunday; any other day moves to the same day next week. Stops closed that day are replaced.", "guess", None),
    ("R7", "Rework", "A replaced stop is swapped for the best candidate of the same kind first, then any kind the pod wants, then any kind.", "guess", None),
    ("R8", "Rework", "If no rework fits within everyone's limits, the plan stays as it is and the next round starts anyway.", "guess", None),
    ("R9", "Rework", "The pod sees what changed (from, to, and a neutral why such as 'Cheaper'), never who asked. Times that only shifted to make room are not listed as changes.", "design", None),

    # ---- Planning and approval
    ("P1", "Planning", "Anyone going can change anything: change a stop, remove it, add one at the end, or reorder. Times recompute. Nothing is voted on.", "design", None),
    ("P2", "Planning", "'Change it to' offers 2 to 4 options, each with a tag (Cheaper, Closer, Quicker, More chill, More active, Something different) and a few words of fact. The options respect the hard limits.", "design", None),
    ("P3", "Planning", "A member's own edit is kept even if it breaks a limit (for example, a reorder that lands on a closed place). The sanity checks then show what broke.", "guess", None),
    ("P4", "Planning", "Anyone who is out can rejoin while it is in Planning: plan as it is, no rework.", "design", None),
    ("P5", "Planning", "Anyone going can leave, with a reason. The plan stays as it is.", "design", None),
    ("P6", "Planning", "When everyone going has approved, the plan is Approved and locked: no edits, no rejoin, no leave.", "manual", None),
    ("P7", "Planning", "An edit does not reset approvals already given.", "guess", None),
    ("P8", "Planning", "A heart belongs to its stop. If the stop is changed, its hearts are cleared.", "design", None),

    # ---- Learning
    ("L1", "Learning", "Not my thing anymore: the member's match on every chip in that plan is multiplied by 0.5 from then on.", "design + guess", "taste_down"),
    ("L2", "Learning", "Done it lately: that plan's places are given a rest for that member (left out of plans they are in).", "design + guess", None),
    ("L3", "Learning", "Not with this group: that plan's places are kept for other pods (left out for this pod).", "design + guess", None),
    ("L4", "Learning", "A heart multiplies the member's match on that stop's chips by 1.2, up to 2x.", "manual + guess", "taste_heart"),
    ("L5", "Learning", "Maybe reasons, practical Can't reasons, silence, limits and needs never move taste. They only steer that plan's rework.", "manual", None),

    # ---- Log
    ("O1", "Log", "Every step is appended to the log and never edited: the request and snapshot, what each filter left, the stops and scores picked, each vote and reason, each rework and what it changed, edits, hearts, approvals, taste nudges and phase changes.", "manual", None),
]

RULES = [{"id": r[0], "stage": r[1], "rule": r[2], "source": r[3], "tune": r[4]} for r in RULES]
