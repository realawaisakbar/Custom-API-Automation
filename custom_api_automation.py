#!/usr/bin/env python3
"""
custom_api_automation.py

Public proof-of-concept: automating data retrieval from a website that has
NO public API, by driving its ordinary HTML login flow the same way a browser
would -- carry the session cookie, read each page's CSRF token, submit the
form, and parse the result.

Target: https://ginandjuice.shop  (PortSwigger's *deliberately vulnerable*
demo shop, published for exactly this kind of testing). The account
carlos / hunter2 is public and shown on the login page itself, so it is
hardcoded below. Do NOT hardcode credentials for any real site -- read them
from the environment instead.

What makes this a nice example:
  * The login is a TWO-STEP wizard -- username first, password second, each
    its own POST -- so you can't shortcut it with a single request.
  * The CSRF token ROTATES on every page, so each step must re-read the fresh
    token from the HTML it just received. Replaying an old token fails.
  * Once authenticated, the order history lives only in server-rendered HTML,
    so we parse it straight out of the page.

Dependencies:  pip install requests

Usage:
    python ginandjuice_scraper.py            # pretty table of past orders
    python ginandjuice_scraper.py --json     # machine-readable output
"""

import re
import html
import json
import time
import argparse

import requests

# TLS trust: on networks with SSL inspection (e.g. a corporate proxy) the chain
# ends in a CA that Windows trusts but Python's bundled certifi does not. If
# `truststore` is installed, route verification through the OS trust store so
# verification stays ON. Harmless off such networks.  pip install truststore
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

BASE = "https://ginandjuice.shop"

# Public demo credentials -- printed on the site's own login page.
# Hardcoded ONLY because this is an intentionally public test target.
USERNAME = "carlos"
PASSWORD = "hunter2"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")


def get_login_csrf(html_text):
    """Pull the CSRF token out of the <form class=login-form ...>.

    The page carries several CSRF tokens (the newsletter form has its own),
    so we anchor to the login form and take the first csrf after it.
    """
    form = re.search(r"<form[^>]*class=login-form.*?</form>", html_text, re.S)
    scope = form.group(0) if form else html_text
    m = re.search(r'name="csrf"\s+value="([^"]+)"', scope)
    if not m:
        raise RuntimeError("Could not find the login-form CSRF token.")
    return m.group(1)


def login(session, attempts=6):
    """Log in, retrying the whole flow on transient failures.

    This public lab sits behind a load balancer and intermittently rejects an
    otherwise-valid login (~1 in 3 tries), bouncing back to /login with
    "Invalid username or password". The failures are independent per attempt,
    so a fresh run from step 1 clears it; a handful of attempts makes the POC
    reliable. (A real target usually needs no such retry.)
    """
    last_err = None
    for n in range(1, attempts + 1):
        try:
            return _login_once(session)
        except RuntimeError as e:
            last_err = e
            session.cookies.clear()      # start each attempt from a clean slate
            time.sleep(0.8)
    raise RuntimeError(f"Login failed after {attempts} attempts: {last_err}")


def _login_once(session):
    """Walk the two-step login wizard, re-reading the CSRF token each step."""
    # Step 1 -- GET /login: establishes the session cookie and hands us the
    # first CSRF token plus the username form.
    r = session.get(f"{BASE}/login", timeout=30)
    r.raise_for_status()
    csrf = get_login_csrf(r.text)

    # Step 2 -- POST the username. The response is the SAME /login URL but now
    # rendered as the password step, carrying a brand-new CSRF token.
    r = session.post(
        f"{BASE}/login",
        data={"csrf": csrf, "username": USERNAME},
        headers={"Origin": BASE, "Referer": f"{BASE}/login"},
        timeout=30,
    )
    r.raise_for_status()
    csrf = get_login_csrf(r.text)  # token rotated -- read the fresh one

    # Step 3 -- POST the password. On success the server replies 302 -> /my-account
    # and swaps in a fresh authenticated session cookie. requests follows the
    # redirect automatically, so r ends up being the My Account page.
    r = session.post(
        f"{BASE}/login",
        data={"csrf": csrf, "username": USERNAME, "password": PASSWORD},
        headers={"Origin": BASE, "Referer": f"{BASE}/login"},
        timeout=30,
    )
    r.raise_for_status()

    if "/logout" not in r.text:
        raise RuntimeError("Login failed -- no authenticated session (check creds/flow).")
    return r.text  # the My Account HTML we were redirected to


def parse_orders(html_text):
    """Extract the order history from the My Account page.

    Each order is one <div class="order-item"> ... </div> block. We pull the
    product name, price, order number, date, status and the details link.
    """
    orders = []
    for block in re.findall(r'<div class="order-item">.*?(?=<div class="order-item">|</section>)',
                            html_text, re.S):
        def grab(pattern, default=""):
            m = re.search(pattern, block, re.S)
            return html.unescape(m.group(1).strip()) if m else default

        product = grab(r"<h3>(.*?)</h3>")
        if not product:
            continue
        orders.append({
            "product": product,
            "price": grab(r'class="order-price">(.*?)</b>'),
            "order_no": grab(r"Order no\.\s*([0-9]+)"),
            "date": grab(r"Order date\s*([0-9/]+)"),
            "status": "Delivered" if "delivered" in block.lower() else "",
            "details_url": BASE + grab(r'href="(/order/details\?orderId=[0-9]+)"'),
        })
    return orders


def main():
    ap = argparse.ArgumentParser(description="Scrape ginandjuice.shop order history (no-API POC).")
    ap.add_argument("--json", action="store_true", help="output JSON instead of a table")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    account_html = login(session)
    orders = parse_orders(account_html)

    if args.json:
        print(json.dumps(orders, indent=2, ensure_ascii=False))
        return

    print(f"\nLogged in as '{USERNAME}' -- order history ({len(orders)} orders):\n")
    print(f"{'#':>2}  {'PRODUCT':<34} {'PRICE':>8}  {'ORDER NO':>9}  {'DATE':<10}  STATUS")
    print("-" * 82)
    for i, o in enumerate(orders, 1):
        print(f"{i:>2}. {o['product']:<34.34} {o['price']:>8}  "
              f"{o['order_no']:>9}  {o['date']:<10}  {o['status']}")
    print()


if __name__ == "__main__":
    main()
