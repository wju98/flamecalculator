def analyze_flame(equip_stats, equip_level):
    """
    Calculates the flame tiers of an equip when given its stats and level. Source for all the flame data is from:
    https://strategywiki.org/wiki/MapleStory/Bonus_Stats. Backtracking algorithm for CSP is heavily inspired by:
    https://leetcode.com/problems/sudoku-solver/discuss/15752/Straight-Forward-Java-Solution-Using-Backtracking.

    :param equip_stats: A list of the equip stats in the following format: [STR, DEX, INT, LUK, MaxHP, MaxMP, Attack,
        Magic Attack, Defense, Speed, Jump, All Stats, Item Level Reduction].
    :param equip_level: An integer that represents the level of the equip.
    :return: A list of the flame tiers in the following format: [STR, DEX, INT, LUK, STR+DEX, STR+INT, STR+LUK, DEX+INT,
        DEX+LUK, INT+LUK, MaxHP, MaxMP, Attack, Magic Attack, Defense, Speed, Jump, All Stats, Item Level Reduction].
        If no such flame tier exists due to inaccurate equip stats or level, an empty list will be returned instead.
    """

    # -1 implies unassigned tier, 0 implies the line does not exist on the flame
    flame_tiers = [-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    num_of_identified_lines = 0

    # calculates all the flame tiers for every stat except for: str, dex, int and luk
    for i in range(4, 13):
        if equip_stats[i] > 0:
            num_of_identified_lines += 1
            if i in [4, 5, 8, 12]:
                if i == 8:
                    # multiplier for defense lines
                    factor = equip_level // 20 + 1
                elif i == 12:
                    # multiplier for item level reduction
                    factor = 5
                else:
                    # multiplier for maxhp/maxmp lines
                    factor = (equip_level // 10) * 30
                    if factor == 0:
                        factor = 3
                tier = equip_stats[i] // factor
            else:
                tier = equip_stats[i]
            flame_tiers[i + 6] = tier

    # if an equip's stats has 0 str, then we know it must have tier 0 on STR, STR+DEX, STR+INT, and STR+LUK
    if equip_stats[0] == 0:
        flame_tiers[0] = flame_tiers[4] = flame_tiers[5] = flame_tiers[6] = 0
    if equip_stats[1] == 0:
        flame_tiers[1] = flame_tiers[4] = flame_tiers[7] = flame_tiers[8] = 0
    if equip_stats[2] == 0:
        flame_tiers[2] = flame_tiers[5] = flame_tiers[7] = flame_tiers[9] = 0
    if equip_stats[3] == 0:
        flame_tiers[3] = flame_tiers[6] = flame_tiers[8] = flame_tiers[9] = 0

    single_stat_multiplier = equip_level // 20 + 1
    pair_stat_multiplier = equip_level // 40 + 1

    min_tier = 1
    if max(flame_tiers) > 5:
        min_tier = 3

    current_tiers = [value for value in flame_tiers if value > 0]
    max_tier = 7
    if len(current_tiers) > 0 and min(current_tiers) < 3:
        max_tier = 5

    # For equips where multiple flame tier solutions exists, we prioritize solutions that don't contain tier 7 (or 
    # tier 5 on non-boss items) due to its extreme low probability of appearing. As a result, we attempt to solve the 
    # flame tiers without considering tier 7 as an option. If no solution is found, we try again including 
    # tier 7 as a possibility.
    if solve_flame(equip_stats, flame_tiers, num_of_identified_lines, single_stat_multiplier,
                   pair_stat_multiplier, min_tier, max_tier, False):
        return flame_tiers

    for x in range(10):
        flame_tiers[x] = -1

    if solve_flame(equip_stats, flame_tiers, num_of_identified_lines, single_stat_multiplier,
                   pair_stat_multiplier, min_tier, max_tier, True):
        return flame_tiers
    else:
        return []


def solve_flame(equip_stats, flame_tiers, num_of_identified_lines, single_stat_multiplier, pair_stat_multiplier,
                min_tier, max_tier, check_t7):
    """
    Helper function for analyze_flame(). The parameter flame_tiers is modified into the correct flame tier solution if
    it exists. Recursive backtracking logic is done using this method.

    :param equip_stats: A list of the equip stats in the following format: [STR, DEX, INT, LUK, MaxHP, MaxMP, Attack,
        Magic Attack, Defense, Speed, Jump, All Stats].
    :param flame_tiers: A list of the flame tiers in the following format: [STR, DEX, INT, LUK, STR+DEX, STR+INT,
        STR+LUK, DEX+INT, DEX+LUK, INT+LUK, MaxHP, MaxMP, Attack, Magic Attack, Defense, Speed, Jump, All Stats].
    :param num_of_identified_lines: Current number of flame tier lines that have been identified.
    :param single_stat_multiplier: Multiplier for flame tier lines with one stat.
    :param pair_stat_multiplier: Multiplier for flame tier lines with a pair of stats. 
    :param min_tier: Current smallest number a flame tier can be.
    :param max_tier: Current largest number a flame tier can be.
    :param check_t7: True if tier 7 (tier 5 for non-boss items) is being considered in search space.
    :return: True if flame tier solution was found, False otherwise.
    """
    tier_adjuster = 0 if check_t7 else 1
    variables = list(range(4, 10)) + list(range(4))
    for i in variables:
        if flame_tiers[i] == -1:
            domain = list(range(max_tier - 1 - tier_adjuster, min_tier, - 1)) + [min_tier, 0, max_tier - tier_adjuster]
            for t in domain:
                if satisfy_constraints(equip_stats, flame_tiers, num_of_identified_lines, single_stat_multiplier,
                                       pair_stat_multiplier, i, t, min_tier):
                    flame_tiers[i] = t
                    new_max_tier = max_tier
                    if t == 1 or t == 2:
                        new_max_tier = 5 - tier_adjuster
                    new_min_tier = min_tier
                    if t == 6 or t == 7:
                        new_min_tier = 3
                    num_lines = num_of_identified_lines
                    if t > 0:
                        num_lines += 1
                    if solve_flame(equip_stats, flame_tiers, num_lines, single_stat_multiplier, pair_stat_multiplier,
                                   new_min_tier, new_max_tier, check_t7):
                        return True
                    else:
                        flame_tiers[i] = -1
            return False
    return True


def satisfy_constraints(equip_stats, flame_tiers, num_of_identified_lines, single_stat_multiplier, pair_stat_multiplier,
                        index, tier, min_tier):
    """
    Helper function for solve_flame(). Tests whether a specific flame line's tier is valid by satisfying the constraints
    that define a flame.

    :param equip_stats: A list of the equip stats in the following format: [STR, DEX, INT, LUK, MaxHP, MaxMP, Attack,
        Magic Attack, Defense, Speed, Jump, All Stats].
    :param flame_tiers: A list of the flame tiers in the following format: [STR, DEX, INT, LUK, STR+DEX, STR+INT,
        STR+LUK, DEX+INT, DEX+LUK, INT+LUK, MaxHP, MaxMP, Attack, Magic Attack, Defense, Speed, Jump, All Stats].
    :param num_of_identified_lines: Current number of flame tier lines that have been identified.
    :param single_stat_multiplier: Multiplier for flame tier lines with one stat.
    :param pair_stat_multiplier: Multiplier for flame tier lines with a pair of stats.
    :param index: Index for flame_tiers on which flame tier line is being tested.
    :param tier: Tier for the flame tier line that is being tested.
    :param min_tier: The current minimum tier any line can be.
    :return: True if all constraints are satisfied, otherwise False.
    """
    # Return False if there are more than three flame tier lines already assigned. Can't have over 4 flame tier lines.
    if num_of_identified_lines > 3 and tier > 0:
        return False

    stat_to_pair = [[4, 5, 6], [4, 7, 8], [5, 7, 9], [6, 8, 9]]

    # Calculates the sum for each stat based off the configuration given by the index and tier.
    for i in range(4):
        incomplete = False
        value = 0
        if index == i:
            value = single_stat_multiplier * tier
        else:
            if flame_tiers[i] == -1:
                incomplete = True
            else:
                value = single_stat_multiplier * flame_tiers[i]
        for j in stat_to_pair[i]:
            if index == j:
                value += tier * pair_stat_multiplier
            else:
                if flame_tiers[j] == -1:
                    incomplete = True
                else:
                    value += flame_tiers[j] * pair_stat_multiplier

        # Return False if the sum of the stats exceeds what the equip's stats are limited to on this configuration..
        if equip_stats[i] < value:
            return False
        # Return False if we have assigned a tier to every flame line and it still doesn't match the equip stats.
        if not incomplete and value != equip_stats[i]:
            return False
        # Return False if we have assigned a tier to every flame, but 4 flames aren't assigned despite being a boss item
        if not incomplete and min_tier == 3 and num_of_identified_lines < 4:
            return False

    return True
