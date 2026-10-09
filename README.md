# custom_api_automation

A small proof-of-concept showing how to **automate data retrieval from a website that has no public API** — by driving its ordinary HTML login flow the same way a browser would: carry the session cookie, read each page's CSRF token, submit the form, and parse the result.

When a service exposes a REST/JSON API, automation is easy. When it doesn't, you're left with the HTML the site renders for humans. This script demonstrates the full pattern against a safe, legal target.

## Target

[`ginandjuice.shop`](https://ginandjuice.shop) — PortSwigger's **deliberately vulnerable** demo shop, published specifically so people can test automation and scanners against it. The demo account `carlos` / `hunter2` is printed on the site's own login page, so it's hardcoded here.

> ⚠️ **This is a learning POC against a sanctioned test site.** Only automate sites you own or are explicitly authorized to test, and never hardcode credentials for a real service — read them from the environment instead (see the note in the script).

## Why it's a useful example

Most "scrape a login" tutorials assume a single POST with a username and password. Real forms are rarely that simple. This one shows three things you'll actually hit:

- **Multi-step login wizard** — the username and password are submitted on *separate* POSTs, so a single request won't authenticate you.
- **Rotating CSRF tokens** — the anti-CSRF token changes on every page, so each step must re-read the fresh token from the HTML it just received. Replaying an old token fails.
- **Cookie-based sessions + redirects** — a `requests.Session` carries the session cookie through the `302` redirect to the account page, exactly like a browser.

It also handles two real-world wrinkles:

- **TLS on inspected networks** — if `truststore` is installed, certificate verification is routed through the OS trust store, so it works behind a corporate SSL-inspection proxy *without* disabling verification.
- **Flaky targets** — the demo lab's load balancer intermittently rejects a valid login; the script retries the flow a few times so the POC stays reliable.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
python custom_api_automation.py          # pretty table of the account's order history
python custom_api_automation.py --json   # same data as JSON
```

### Sample output

```
Logged in as 'carlos' -- order history (5 orders):

 #  PRODUCT                               PRICE   ORDER NO  DATE        STATUS
----------------------------------------------------------------------------------
 1. Sloe Gin Timer Kit                   $85.78    0254809  10/04/2024  Delivered
 2. Create Your Own Cocktail             $84.96    0254791  9/27/2024   Delivered
 3. Fruit Curliwurlier                   $20.86    0254774  9/03/2024   Delivered
 4. Fruit Slicer (Limited Edition)       $21.26    0254725  9/02/2024   Delivered
 5. Flamin’ Cocktail Glasses             $69.81    0254685  8/28/2024   Delivered
```

## How it works

1. `GET /login` — establishes the session cookie and returns the first CSRF token + username form.
2. `POST /login` with the username — returns the same URL re-rendered as the password step, carrying a **new** CSRF token.
3. `POST /login` with the username + password — on success the server replies `302 → /my-account`; `requests` follows the redirect automatically.
4. Parse the order history out of the returned HTML.

## License

MIT — use it freely for learning.
