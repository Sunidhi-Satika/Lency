"""Exact maths, unit conversion and currency conversion: no LLM guessing at arithmetic.

parse(text)  -> None, or a small description of what was asked (pure text work, no network;
                the router uses it to decide whether a sentence is a calculation at all)
answer(text) -> one spoken-style sentence, or None if it turns out not to be a calculation
"""
import ast
import math
import operator
import re
import time

import requests

# ------------------------------------------------------------------ safe arithmetic
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.USub: operator.neg, ast.UAdd: operator.pos,
        ast.FloorDiv: operator.floordiv}
_FUNCS = {"sqrt": math.sqrt, "abs": abs, "round": round, "sin": lambda x: math.sin(math.radians(x)),
          "cos": lambda x: math.cos(math.radians(x)), "tan": lambda x: math.tan(math.radians(x)),
          "log": math.log10, "ln": math.log, "factorial": math.factorial}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(b) > 1000:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and len(node.args) == 1:
        return _FUNCS[node.func.id](_eval(node.args[0]))
    raise ValueError("unsupported")


_NUMWORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
             "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
             "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_MULTI = {"hundred": 100, "thousand": 1000, "million": 10**6, "billion": 10**9}


def _words_to_numbers(text):
    """'twenty five times three hundred' -> '25 times 300' (small, handles the common spoken forms)."""
    tokens, out, i = text.split(), [], 0
    while i < len(tokens):
        t = tokens[i]
        if t in _NUMWORDS or (t in _MULTI and False):
            total, cur = 0, 0
            while i < len(tokens) and (tokens[i] in _NUMWORDS or tokens[i] in _MULTI or tokens[i] == "and"):
                w = tokens[i]
                if w == "and":
                    if not (i + 1 < len(tokens) and tokens[i + 1] in _NUMWORDS):
                        break
                elif w in _NUMWORDS:
                    cur += _NUMWORDS[w]
                elif w == "hundred":
                    cur = max(cur, 1) * 100
                else:
                    total += max(cur, 1) * _MULTI[w]
                    cur = 0
                i += 1
            out.append(str(total + cur))
            continue
        out.append(t)
        i += 1
    return " ".join(out)


_LEAD = re.compile(r"^(?:hey lency[, ]*|lency[, ]*|please |can you |could you |tell me |calculate |compute |work out |"
                   r"what(?:'s| is| are) |how much is |how much are |whats |solve )+", re.I)


def _to_expression(text):
    t = text.lower().strip(" ?!.")
    t = _LEAD.sub("", t)
    t = _words_to_numbers(t)
    t = re.sub(r"(\d)\s*,\s*(?=\d{3}\b)", r"\1", t)                         # 1,200 -> 1200
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)\s+of\s+(\d+(?:\.\d+)?)", r"((\1/100)*\2)", t)
    t = re.sub(r"square root of\s+(\d+(?:\.\d+)?)", r"sqrt(\1)", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:squared)", r"(\1**2)", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*(?:cubed)", r"(\1**3)", t)
    for a, b in ((r"\bto the power(?: of)?\b|\braised to\b|\bpower\b|\^", "**"), (r"\bmultiplied by\b|\btimes\b|\binto\b|\bx\b", "*"),
                 (r"\bdivided by\b|\bover\b", "/"), (r"\bplus\b|\band\b", "+"), (r"\bminus\b|\bsubtract\b|\bless\b", "-"),
                 (r"\bmodulo\b|\bmod\b", "%")):
        t = re.sub(a, f" {b} ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


_ALLOWED = re.compile(r"^[\d\s+\-*/%().a-z]+$")


def _parse_math(text):
    expr = _to_expression(text)
    if not re.search(r"\d", expr) or not re.search(r"[+\-*/%]|sqrt\(", expr) or not _ALLOWED.match(expr):
        return None
    if re.search(r"[a-z]+", re.sub(r"sqrt|abs|round|sin|cos|tan|log|ln|factorial", "", expr)):
        return None                                            # leftover words: not a calculation
    try:
        tree = ast.parse(expr, mode="eval")
        value = _eval(tree)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
        return None
    return ("math", expr, value)


def _fmt(x):
    if isinstance(x, float):
        if x != x or x in (float("inf"), float("-inf")):
            return "not a number"
        if abs(x - round(x)) < 1e-9:
            x = int(round(x))
        else:
            x = float(f"{x:.6g}") if abs(x) < 1e6 else round(x, 2)
    if isinstance(x, int):
        return f"{x:,}".replace(",", "") if abs(x) < 10000 else f"{x:,}"
    return str(x)


# ------------------------------------------------------------------ units
# unit -> (category, factor to the category's base unit); temperature is handled separately
_UNITS = {}


def _reg(cat, factor, *names):
    for n in names:
        _UNITS[n] = (cat, factor)


_reg("length", 1, "meter", "meters", "metre", "metres", "m")
_reg("length", 1000, "kilometer", "kilometers", "kilometre", "kilometres", "km", "kms")
_reg("length", 0.01, "centimeter", "centimeters", "centimetre", "centimetres", "cm")
_reg("length", 0.001, "millimeter", "millimeters", "mm")
_reg("length", 1609.344, "mile", "miles", "mi")
_reg("length", 0.9144, "yard", "yards", "yd")
_reg("length", 0.3048, "foot", "feet", "ft")
_reg("length", 0.0254, "inch", "inches", "in")
_reg("mass", 1, "kilogram", "kilograms", "kg", "kgs", "kilo", "kilos")
_reg("mass", 0.001, "gram", "grams", "g")
_reg("mass", 0.000001, "milligram", "milligrams", "mg")
_reg("mass", 0.45359237, "pound", "pounds", "lb", "lbs")
_reg("mass", 0.028349523, "ounce", "ounces", "oz")
_reg("mass", 1000, "tonne", "tonnes", "ton", "tons")
_reg("volume", 1, "liter", "liters", "litre", "litres", "l")
_reg("volume", 0.001, "milliliter", "milliliters", "millilitre", "millilitres", "ml")
_reg("volume", 3.785411784, "gallon", "gallons", "gal")
_reg("volume", 0.2365882365, "cup", "cups")
_reg("volume", 0.0295735, "fluid ounce", "fluid ounces", "floz")
_reg("volume", 0.0147868, "tablespoon", "tablespoons", "tbsp")
_reg("volume", 0.00492892, "teaspoon", "teaspoons", "tsp")
_reg("speed", 1, "meters per second", "m/s", "mps")
_reg("speed", 0.277778, "kilometers per hour", "kilometres per hour", "km/h", "kph", "kmh", "kmph")
_reg("speed", 0.44704, "miles per hour", "mph")
_reg("speed", 0.514444, "knot", "knots")
_reg("time", 1, "second", "seconds", "sec", "secs")
_reg("time", 60, "minute", "minutes", "min", "mins")
_reg("time", 3600, "hour", "hours", "hr", "hrs")
_reg("time", 86400, "day", "days")
_reg("time", 604800, "week", "weeks")
_reg("data", 1, "byte", "bytes")
_reg("data", 1024, "kilobyte", "kilobytes", "kb")
_reg("data", 1024 ** 2, "megabyte", "megabytes", "mb")
_reg("data", 1024 ** 3, "gigabyte", "gigabytes", "gb")
_reg("data", 1024 ** 4, "terabyte", "terabytes", "tb")
_reg("area", 1, "square meter", "square meters", "sqm")
_reg("area", 10000, "hectare", "hectares")
_reg("area", 4046.8564, "acre", "acres")
_reg("area", 0.09290304, "square foot", "square feet", "sqft")
_TEMP = {"celsius": "c", "centigrade": "c", "c": "c", "degrees celsius": "c", "fahrenheit": "f", "f": "f",
         "degrees fahrenheit": "f", "kelvin": "k", "k": "k"}

# currency: code, and the words people say
_CUR_WORDS = {"dollar": "USD", "dollars": "USD", "usd": "USD", "bucks": "USD", "rupee": "INR", "rupees": "INR",
              "inr": "INR", "euro": "EUR", "euros": "EUR", "eur": "EUR", "gbp": "GBP", "sterling": "GBP",
              "pound sterling": "GBP", "yen": "JPY", "jpy": "JPY", "yuan": "CNY", "cny": "CNY", "rmb": "CNY",
              "aud": "AUD", "cad": "CAD", "chf": "CHF", "franc": "CHF", "francs": "CHF", "dirham": "AED",
              "dirhams": "AED", "aed": "AED", "won": "KRW", "krw": "KRW", "sgd": "SGD", "rand": "ZAR", "zar": "ZAR",
              "taka": "BDT", "bdt": "BDT", "baht": "THB", "thb": "THB", "peso": "MXN", "pesos": "MXN", "mxn": "MXN"}
_CUR_NAMES = {"USD": "US dollars", "INR": "rupees", "EUR": "euros", "GBP": "pounds", "JPY": "yen", "CNY": "yuan",
              "AUD": "Australian dollars", "CAD": "Canadian dollars", "CHF": "Swiss francs", "AED": "dirhams",
              "KRW": "won", "SGD": "Singapore dollars", "ZAR": "rand", "BDT": "taka", "THB": "baht", "MXN": "pesos"}

_NUM = r"-?\d+(?:,\d{3})*(?:\.\d+)?|-?\.\d+"
_CONV = re.compile(rf"^(?:convert\s+|what(?:'s| is)\s+|how (?:much|many) is\s+)?({_NUM})\s*(?:degrees?\s+|°\s*)?([a-z/ ]+?)\s+(?:to|in|into|as)\s+(?:degrees?\s+|°\s*)?([a-z/ ]+?)$")
_HOWMANY = re.compile(rf"^how (?:many|much)\s+([a-z/ ]+?)\s+(?:are |is )?(?:there )?in\s+(?:an?\s+|one\s+)?({_NUM})?\s*([a-z/ ]+?)$")


def _unit_key(name):
    n = re.sub(r"\s+", " ", name.strip().lower())
    n = re.sub(r"^(?:the|a|an)\s+", "", n)
    if n in _TEMP:
        return ("temp", _TEMP[n])
    if n in _UNITS:
        return ("unit", n)
    if n.endswith("s") and n[:-1] in _UNITS:
        return ("unit", n[:-1])
    return None


def _cur_key(name):
    n = re.sub(r"\s+", " ", name.strip().lower())
    return _CUR_WORDS.get(n)


def _parse_convert(text):
    t = re.sub(r"\s+", " ", text.lower().strip(" ?!."))
    t = re.sub(r"^(?:hey lency[, ]*|lency[, ]*|please |can you |could you |tell me )+", "", t)
    value = src = dst = None
    m = _HOWMANY.match(t)
    if m:
        dst, value, src = m.group(1), m.group(2) or "1", m.group(3)
    else:
        m = _CONV.match(t)
        if m:
            value, src, dst = m.group(1), m.group(2), m.group(3)
    if value is None:
        return None
    value = float(value.replace(",", ""))
    sc, dc = _cur_key(src), _cur_key(dst)
    su, du = _unit_key(src), _unit_key(dst)
    if sc and dc:
        return ("currency", value, sc, dc)
    if su and du:
        if su[0] == "temp" and du[0] == "temp":
            return ("temp", value, su[1], du[1])
        if su[0] == "unit" and du[0] == "unit" and _UNITS[su[1]][0] == _UNITS[du[1]][0]:
            return ("unit", value, su[1], du[1])
    return None


def parse(text):
    if not text or not re.search(r"\d|\bhow (?:many|much)\b|\b(?:" + "|".join(_NUMWORDS) + r")\b", text.lower()):
        return None
    return _parse_convert(text) or _parse_math(text)


# ------------------------------------------------------------------ currency rates (cached, free, no key)
_rates = {"t": 0, "data": {}}


def _rate(src, dst):
    if time.time() - _rates["t"] > 6 * 3600 or src not in _rates["data"]:
        r = requests.get(f"https://open.er-api.com/v6/latest/{src}", timeout=6)
        r.raise_for_status()
        _rates["data"][src] = r.json()["rates"]
        _rates["t"] = time.time()
    return _rates["data"][src][dst]


def _temp(v, a, b):
    c = v if a == "c" else (v - 32) * 5 / 9 if a == "f" else v - 273.15
    return c if b == "c" else c * 9 / 5 + 32 if b == "f" else c + 273.15


_TNAME = {"c": "degrees Celsius", "f": "degrees Fahrenheit", "k": "kelvin"}


def answer(text):
    p = parse(text)
    if not p:
        return None
    kind = p[0]
    try:
        if kind == "math":
            return f"That's {_fmt(p[2])}."
        if kind == "temp":
            return f"{_fmt(p[1])} {_TNAME[p[2]]} is {_fmt(_temp(p[1], p[2], p[3]))} {_TNAME[p[3]]}."
        if kind == "unit":
            _, v, a, b = p
            ca, fa = _UNITS[a]
            _, fb = _UNITS[b]
            out = v * fa / fb
            return f"{_fmt(v)} {a} is about {_fmt(round(out, 4) if abs(out) < 1e6 else out)} {b}."
        if kind == "currency":
            _, v, a, b = p
            out = v * _rate(a, b)
            return f"{_fmt(v)} {_CUR_NAMES.get(a, a)} is about {_fmt(round(out, 2))} {_CUR_NAMES.get(b, b)} at today's rate."
    except requests.RequestException:
        return "I couldn't fetch the exchange rate right now. Check your connection and try again."
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    return None


if __name__ == "__main__":
    for t in ["what's 15% of 80", "twelve times seven", "2 to the power 10", "square root of 144",
              "convert 5 miles to km", "72 fahrenheit to celsius", "how many km in 3 miles", "100 usd to inr"]:
        print(t, "->", answer(t))
