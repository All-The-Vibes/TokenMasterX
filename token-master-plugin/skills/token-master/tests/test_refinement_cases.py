"""Independent exact cross-checks use only public problem data."""
from collections import Counter, defaultdict
from dataclasses import FrozenInstanceError, asdict, fields, replace
from fractions import Fraction
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "evals"))
from refinement.cases import Case, generate_cases, grade_answer, normalize_answer  # noqa: E402


def problem(case):
    return json.loads(case.prompt.split("\nData: ", 1)[1].split("\n", 1)[0])


def scheduling(d):
    # Forward subset DP, retaining elapsed time and last job, rather than orders.
    states = {(0, -1, 0): 1}
    for _ in range(6):
        next_states = defaultdict(int)
        for (mask, last, time), ways in states.items():
            for job in range(6):
                if mask & (1 << job):
                    continue
                first, second = d["before"]
                if job == second and not mask & (1 << first):
                    continue
                finish = time + d["duration"][job]
                if last >= 0 and d["groups"][last] != d["groups"][job]:
                    finish += d["setup"]
                if finish <= d["deadlines"][job]:
                    next_states[mask | (1 << job), job, finish] += ways
        states = next_states
    return sum(states.values())


def path_counting(d):
    # Enumerate positions of D and R in the step sequence; remaining steps are U.
    diagonal = d["diagonals"]
    right = d["width"] - diagonal
    length = d["width"] + d["height"] - diagonal
    blocked = {tuple(point) for point in d["blocked"]}
    result = 0
    for ds in combinations(range(length), diagonal):
        ds = set(ds)
        for rs in combinations([i for i in range(length) if i not in ds], right):
            rs = set(rs)
            x, y = 0, 0
            for i in range(length):
                x += i in ds or i in rs
                y += i not in rs
                if (x, y) in blocked:
                    break
            else:
                assert (x, y) == (d["width"], d["height"])
                result += 1
    return result


def probability(d):
    # Enumerate subsets of individually labelled balls, not color multiplicities.
    colors = [color for color, count in enumerate(d["populations"])
              for _ in range(count)]
    numerator = denominator = 0
    for selected in combinations(range(len(colors)), d["draws"]):
        draw = [colors[i] for i in selected]
        if 0 in draw and 1 in draw:
            denominator += 1
            numerator += draw.count(2) % 2 == 0 and sum(c + 1 for c in draw) >= d["threshold"]
    return Fraction(numerator, denominator)


def integer_optimization(d):
    # Bounded 0/1 knapsack over individual copies, not quantity-vector enumeration.
    states = {(0, 0, 0): 0}
    for i, limit in enumerate(d["limits"]):
        for _ in range(limit):
            updated = dict(states)
            for (a, b, n), score in states.items():
                key = (a + d["costs"][i][0], b + d["costs"][i][1], n + 1)
                if key[0] <= d["capacity"][0] and key[1] <= d["capacity"][1] and key[2] <= d["max_units"]:
                    updated[key] = max(updated.get(key, 0), score + d["values"][i])
            states = updated
    return max(score for (_, _, n), score in states.items() if n % 2 == 0)


CHECKS = dict(scheduling=scheduling, path_counting=path_counting,
              probability=probability, integer_optimization=integer_optimization)


@pytest.mark.parametrize("seed", [0, 1, 7, 42, -901, 2**80])
def test_independent_oracles(seed):
    for case in generate_cases(seed, 16):
        expected = CHECKS[case.family](problem(case))
        assert Fraction(case.expected) == expected
        assert str(Fraction(case.expected)) == case.expected
        assert grade_answer(case, case.expected)
        assert not grade_answer(case, str(expected + 1))


def test_schema_identity_frozen_and_deterministic():
    state = random.getstate()
    cases = generate_cases(123)
    assert random.getstate() == state
    assert cases == generate_cases(123)
    assert len(cases) == 8
    assert Counter(case.family for case in cases) == {family: 2 for family in CHECKS}
    assert len({case.id for case in cases}) == len({case.identity for case in cases}) == 8
    assert [field.name for field in fields(Case)] == ["id", "family", "prompt", "expected"]
    for case, changed_seed in zip(cases, generate_cases(124)):
        assert case.prompt != changed_seed.prompt
        assert case.identity != changed_seed.identity
        assert re.fullmatch("[0-9a-f]{64}", case.identity)
        payload = json.dumps(asdict(case), sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        assert case.identity == hashlib.sha256(payload).hexdigest()
        for field in fields(Case):
            assert replace(case, **{field.name: getattr(case, field.name) + "x"}).identity != case.identity
        with pytest.raises(FrozenInstanceError):
            case.expected = "0"


@pytest.mark.parametrize("count", range(4, 17))
def test_count_cycle_prefix_and_no_duplicates(count):
    cases = generate_cases(57, count)
    assert len(cases) == count
    assert cases == generate_cases(57, 16)[:count]
    assert [case.family for case in cases] == [list(CHECKS)[i % 4] for i in range(count)]
    assert len({case.prompt for case in cases}) == count


@pytest.mark.parametrize("seed", [True, False, None, "1", 1.5, [], {}])
def test_invalid_seed(seed):
    with pytest.raises(ValueError):
        generate_cases(seed)


@pytest.mark.parametrize("count", [True, False, None, "8", 8.0, -1, 0, 3, 17, 10**9])
def test_invalid_count(count):
    with pytest.raises(ValueError):
        generate_cases(0, count)


@pytest.mark.parametrize("answer", [
    None, True, False, 2, 2.0, Fraction(2), float("nan"), [], {}, b"2",
    "", " ", "2.0", "2e0", "NaN", "Infinity", "2/0", "2/-1", "2/+1",
    "+2", "02", "2/01", "-0", "2//1", "2 / 1", "2/1/1", "1+1",
    "abs(2)", "__import__('os').getcwd()", "```2```", "Answer: 2",
    "٢", "２", "2\n0", "2\x00", "2" + " " * 128, "9" * 129,
])
def test_bounded_parser_rejects_non_numeric_or_malformed(answer):
    assert normalize_answer(answer) is None
    assert grade_answer(Case("id", "test", "prompt", "2"), answer) is False


@pytest.mark.parametrize(("expected", "answer"), [
    ("2", "4/2"), ("2", "\n 2/1 \t"), ("-2", "-6/3"), ("0", "0/9"),
    ("2/3", "10/15"), ("-2/3", "-10/15"), ("9" * 128, "9" * 128),
])
def test_equivalent_exact_values(expected, answer):
    assert normalize_answer(answer) == expected
    assert grade_answer(Case("id", "test", "prompt", expected), answer) is True


def test_parser_checks_bounds_and_grammar_before_fraction(monkeypatch):
    from refinement import cases as module

    def forbidden_parse(_):
        pytest.fail("rejected input reached Fraction")

    monkeypatch.setattr(module, "Fraction", forbidden_parse)
    for answer in ["9" * 129, " " * 128 + "2", "1+1", "1/0", "NaN", True, 2.0]:
        assert module.normalize_answer(answer) is None


def test_normalized_plurality_needs_no_case_or_expected_answer():
    answers = ["2/3", "4/6", "0.666666", "6/9", "3/4", "bad"]
    counts = Counter(value for answer in answers
                     if (value := normalize_answer(answer)) is not None)
    assert counts == {"2/3": 3, "3/4": 1}
    assert all(normalize_answer(value) == value for value in counts)


def test_prompt_contains_only_problem_data_and_output_contract():
    allowed_keys = {
        "scheduling": {"duration", "groups", "setup", "deadlines", "before"},
        "path_counting": {"width", "height", "blocked", "diagonals"},
        "probability": {"populations", "draws", "threshold"},
        "integer_optimization": {"costs", "values", "limits", "capacity", "max_units"},
    }
    for case in generate_cases(901, 16):
        statement, data, output = case.prompt.splitlines()
        assert set(problem(case)) == allowed_keys[case.family]
        assert data.startswith("Data: ")
        assert output == (
            "The numeric answer must be an integer or a reduced fraction p/q with a positive "
            "denominator, never a decimal, units, or code. "
            "Use the response format requested by the evaluator."
        )
        assert not re.search(r"\b(expected|gold|oracle|solution|answer key)\b", case.prompt, re.I)
        assert statement and "```" not in case.prompt
        # Private answers and identifiers never get interpolated into instructions.
        mutated = replace(case, expected="PRIVATE_ORACLE_CANARY", id="PRIVATE_ID_CANARY")
        assert mutated.prompt == case.prompt


def test_no_answer_based_selection(monkeypatch):
    from refinement import cases as module

    calls = []

    def build(rng):
        calls.append(rng.randrange(100))
        return {"n": calls[-1]}, "Find n.", 0

    monkeypatch.setattr(module, "_FAMILIES", tuple((name, build) for name in CHECKS))
    cases = module.generate_cases(11, 16)
    assert len(calls) == len(cases) == 16
    assert all(case.expected == "0" for case in cases)
