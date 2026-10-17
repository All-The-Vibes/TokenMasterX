"""Seeded no-tools mathematics tasks; expected values stay evaluator-side.

Only ``case.prompt`` is model input. Identities bind all four stored fields,
including the private answer, using canonical JSON and SHA256.
"""
from dataclasses import asdict, dataclass
from fractions import Fraction
from functools import lru_cache
import hashlib
from itertools import permutations, product
import json
from math import comb
import random
import re


@dataclass(frozen=True)
class Case:
    id: str
    family: str
    prompt: str
    expected: str

    @property
    def identity(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_OUTPUT = (
    "The numeric answer must be an integer or a reduced fraction p/q with a positive "
    "denominator, never a decimal, units, or code. "
    "Use the response format requested by the evaluator."
)
_NUMBER = re.compile(r"(?:0|-?[1-9][0-9]*)(?:/[1-9][0-9]*)?", re.ASCII)


def normalize_answer(answer: object) -> str | None:
    """Canonicalize bounded integer/fraction text without any oracle access.

    Outer whitespace and equivalent fractions are accepted. Decimal notation,
    leading zeros, signed denominators, and non-string objects are rejected.
    """
    if type(answer) is not str or len(answer) > 128:
        return None
    text = answer.strip()
    if _NUMBER.fullmatch(text) is None:
        return None
    return str(Fraction(text))


def grade_answer(case: Case, answer: object) -> bool:
    """Compare exact values; accept equivalent fractions and outer whitespace.

    Only bounded text matching the integer/fraction grammar is parsed. No
    expressions, decimal coercion, Python evaluation, or model code execution.
    """
    actual, expected = normalize_answer(answer), normalize_answer(case.expected)
    return actual is not None and expected is not None and actual == expected


def _scheduling(rng: random.Random) -> tuple[dict, str, int]:
    duration = [rng.randint(1, 4) for _ in range(6)]
    groups = [rng.randrange(2) for _ in range(6)]
    setup = rng.randint(1, 3)
    elapsed, deadlines = 0, []
    for j in range(6):
        elapsed += duration[j] + (setup if j and groups[j] != groups[j - 1] else 0)
        deadlines.append(elapsed + rng.randint(1, 6))
    before = sorted(rng.sample(range(6), 2))
    data = dict(duration=duration, groups=groups, setup=setup,
                deadlines=deadlines, before=before)
    count = 0
    for order in permutations(range(6)):
        if order.index(before[0]) > order.index(before[1]):
            continue
        time, valid = 0, True
        for k, j in enumerate(order):
            time += duration[j]
            if k and groups[j] != groups[order[k - 1]]:
                time += setup
            if time > deadlines[j]:
                valid = False
                break
        count += valid
    text = (
        "Six distinct jobs numbered 0 through 5 run once each on one machine. "
        "Start at time 0, with no idle time and no setup before the first job. "
        "Between consecutive jobs in different groups, spend setup time; otherwise "
        "spend none. A job's completion time includes all preceding setup and work. "
        "Every completion must be at most that job's deadline. The first job in "
        "before must occur earlier than the second (not necessarily immediately). "
        "How many job orders satisfy all these conditions?"
    )
    return data, text, count


def _path_counting(rng: random.Random) -> tuple[dict, str, int]:
    width, height = rng.randint(5, 7), rng.randint(5, 7)
    blocked = sorted(rng.sample([(x, y) for x in range(1, width)
                                for y in range(1, height)], 4))
    diagonals = rng.randint(1, 3)
    data = dict(width=width, height=height, blocked=blocked, diagonals=diagonals)
    forbidden = set(blocked)

    @lru_cache(None)
    def paths(x, y, left):
        if x > width or y > height or left < 0 or (x, y) in forbidden:
            return 0
        if (x, y) == (width, height):
            return int(left == 0)
        return paths(x + 1, y, left) + paths(x, y + 1, left) + paths(x + 1, y + 1, left - 1)

    text = (
        "Count paths on integer lattice points from (0,0) to (width,height). "
        "Each step is R=(1,0), U=(0,1), or D=(1,1). Stay inside the rectangle, "
        "never land on a blocked point, and use exactly diagonals D steps. "
        "Only landing points are checked: a diagonal may pass beside blocked "
        "points. Distinct step sequences count as distinct paths."
    )
    return data, text, paths(0, 0, diagonals)


def _probability(rng: random.Random) -> tuple[dict, str, Fraction]:
    populations = [rng.randint(3, 6) for _ in range(3)]
    draws, threshold = rng.randint(5, 6), rng.randint(9, 14)
    data = dict(populations=populations, draws=draws, threshold=threshold)
    favorable, conditional = 0, 0
    for red in range(1, min(draws, populations[0]) + 1):
        for blue in range(1, min(draws - red, populations[1]) + 1):
            green = draws - red - blue
            if not 0 <= green <= populations[2]:
                continue
            ways = comb(populations[0], red) * comb(populations[1], blue) * comb(populations[2], green)
            conditional += ways
            if green % 2 == 0 and red + 2 * blue + 3 * green >= threshold:
                favorable += ways
    text = (
        "An urn contains populations of red, blue, and green balls, in that order. "
        "All individual balls are equally likely to be selected. Draw draws balls "
        "uniformly without replacement. Red, blue, and green balls score 1, 2, "
        "and 3 points respectively. Given that the draw contains at least one "
        "red AND at least one blue ball, what is the probability that the number "
        "of green balls is even AND the total score is at least threshold?"
    )
    return data, text, Fraction(favorable, conditional)


def _integer_optimization(rng: random.Random) -> tuple[dict, str, int]:
    costs = [[rng.randint(2, 6), rng.randint(2, 6)] for _ in range(3)]
    values = rng.sample(range(5, 16), 3)
    limits = [rng.randint(3, 6) for _ in range(3)]
    capacity = [rng.randint(18, 26), rng.randint(18, 26)]
    max_units = rng.randint(6, 9)
    data = dict(costs=costs, values=values, limits=limits,
                capacity=capacity, max_units=max_units)
    best = 0
    for quantities in product(*(range(limit + 1) for limit in limits)):
        units = sum(quantities)
        if units > max_units or units % 2:
            continue
        if any(sum(quantities[i] * costs[i][r] for i in range(3)) > capacity[r]
               for r in range(2)):
            continue
        best = max(best, sum(q * value for q, value in zip(quantities, values)))
    text = (
        "Choose nonnegative integer quantities of three item types, indexed 0,1,2. "
        "Each type i consumes costs[i][0] and costs[i][1] units of two resources "
        "per item, and earns values[i] points per item. Quantity i must be at most "
        "limits[i]. Resource totals must not exceed the corresponding capacity. "
        "The total number of items must be even and at most max_units; choosing "
        "zero items is allowed. What is the maximum total points?"
    )
    return data, text, best


_FAMILIES = (
    ("scheduling", _scheduling),
    ("path_counting", _path_counting),
    ("probability", _probability),
    ("integer_optimization", _integer_optimization),
)


def generate_cases(seed: int, count: int = 8) -> list[Case]:
    """Generate 4..16 cases, cycling families without answer-based selection.

    Prefixes are stable across counts. A local RNG never changes global random
    state. Each cycle generates fresh parameter variations of the four tasks.
    """
    if type(seed) is not int:
        raise ValueError("seed must be an integer, not a boolean")
    if type(count) is not int or not 4 <= count <= 16:
        raise ValueError("count must be an integer in 4..16")
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        family, build = _FAMILIES[index % len(_FAMILIES)]
        data, statement, expected = build(rng)
        prompt = f"{statement}\nData: {json.dumps(data, sort_keys=True, separators=(',', ':'))}\n{_OUTPUT}"
        cases.append(Case(f"{family}-{index // 4 + 1:02d}", family, prompt, str(expected)))
    return cases
