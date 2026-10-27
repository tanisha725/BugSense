# Demo services

Three tiny programs that act as a small online shop, so BugSense has a real
system to monitor (BugSense starts and watches them on the **Services** page).
They use only Python's standard library.

| Program | Port | Job |
|---|---|---|
| `shop_db.py` | 9102 | A pretend database |
| `shop_api.py` | 9101 | Checkout API, asks shop-db for every order |
| `shop_web.py` | - | Acts like customers: one checkout per second |

A checkout goes shop-web → shop-api → shop-db, carrying one request ID.

`shop_api.py` can be started with a fault, using the `SHOP_FAULT` variable:

| `SHOP_FAULT` | What happens |
|---|---|
| `crash` | Starts, then crashes with an unhandled error, again and again |
| `bad-config` | Refuses to start because of a broken database address |
| `slow` | Many requests hang, and some time out |

Stopping `shop_db.py` shows what happens when the database goes down.
