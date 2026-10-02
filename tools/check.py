#!/usr/bin/env python3
"""Static consistency checks for index.html (single-file site).

Usage: python3 tools/check.py [path/to/index.html]
Exits non-zero if any check fails.
"""
import collections
import json
import re
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "index.html"
src = open(path, encoding="utf-8").read()
fails = []


def fail(msg):
    fails.append(msg)


tpls = dict(re.findall(r'<template data-route="([^"]+)"[^>]*>(.*?)</template>', src, re.S))
routes = set(tpls)

# Images: every data-img key must resolve to an inline <img src> or the window.__IMG map
static_imgs = set(re.findall(r'<img src="data:[^"]+" data-img="([^"]+)"', src))
m = re.search(r"window\.__IMG=(\{.*?\});</script>", src, re.S)
img_map = set(json.loads(m.group(1))) if m else set()
for key in set(re.findall(r'data-img="([^"]+)"', src)) - static_imgs - img_map:
    fail(f"image key not embedded: {key}")


# Internal links / form actions must point at an existing route
def norm(p):
    p = p.split("?")[0].split("#")[0]
    return p if p.endswith((".html", "/")) else p + "/"


for href in set(re.findall(r'(?:href|action)="(/[^/"][^"]*|/)"', src)):
    if norm(href) not in routes:
        fail(f"broken internal link: {href}")

# Per page: exactly one h1, unique ids, aria-labelledby targets exist
main = re.search(r'<main id="main">(.*?)</main>', src, re.S).group(1)
pages = dict(tpls, **{"(static home)": main})
for route, body in pages.items():
    ids = collections.Counter(re.findall(r'\sid="([^"]+)"', body))
    for i, n in ids.items():
        if n > 1:
            fail(f"{route}: duplicate id #{i}")
    for t in re.findall(r'aria-labelledby="([^"]+)"', body):
        if t not in ids:
            fail(f"{route}: aria-labelledby target #{t} missing")
    if len(re.findall(r"<h1[\s>]", body)) != 1:
        fail(f"{route}: expected exactly one <h1>")

# Static home markup must match the "/" template (it is shown on first load instead of the template)
if re.sub(r'<img src="data:[^"]+" ', "<img ", main).strip() != tpls["/"].strip():
    fail('static <main> differs from <template data-route="/">')


# Catalog consistency: every listing page shows exactly the cards the /products/ data implies
def cards(body):
    return [dict(re.findall(r'data-(pid|brand|cat|size|ind)="([^"]*)"', a))
            for a in re.findall(r'<article class="card"([^>]*)>', body)]


catalog = cards(tpls["/products/"])
pids = [c["pid"] for c in catalog]
product_routes = {r.split("/")[2] for r in routes if r.startswith("/products/") and r != "/products/"}
if set(pids) != product_routes or len(pids) != len(set(pids)):
    fail(f"/products/ cards {sorted(pids)} != product routes {sorted(product_routes)}")
if f"สินค้าทั้งหมด {len(pids)} รายการ" not in src:
    fail(f"product total {len(pids)} not reflected in page copy")

for route, body in tpls.items():
    kind, _, key = route.strip("/").partition("/")
    if not key or kind not in ("categories", "industries", "brands"):
        continue
    field = {"categories": "cat", "industries": "ind", "brands": "brand"}[kind]
    want = sorted(c["pid"] for c in catalog if key in c[field].split())
    got = sorted(c["pid"] for c in cards(body))
    if want != got:
        fail(f"{route}: cards {got} != expected {want}")
    # "N รายการ" labels that link to this page must match
    for n in re.findall(rf'href="{re.escape(route)}"><span[^>]*>(?:<span class="cat__txt">)?<(?:span|strong)[^>]*>[^<]+</(?:span|strong)><(?:span|small)[^>]*>(\d+) รายการ', src):
        if int(n) != len(want):
            fail(f"link to {route} says {n} รายการ, actual {len(want)}")

# Filter <select> options must cover every value used on cards
form = re.search(r'<form id="filters".*?</form>', tpls["/products/"], re.S).group(0)
for name, opts in re.findall(r'<select name="(\w+)">(.*?)</select>', form, re.S):
    values = set(re.findall(r'<option value="([^"]+)"', opts))
    used = {v for c in catalog for v in c[name].split()}
    if used - values:
        fail(f"filter '{name}' missing options for {sorted(used - values)}")

if 'name="robots" content="noindex"' in src:
    fail("robots noindex present (blocks search engines on the live site)")

print(f"{len(routes)} routes, {len(pids)} products checked")
for f in fails:
    print("FAIL", f)
sys.exit(1 if fails else 0)
