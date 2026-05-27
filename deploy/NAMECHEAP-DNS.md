# Namecheap DNS — worldcupytu.org

If `curl -I http://worldcupytu.org` shows:

- `X-Served-By: Namecheap URL Forward`
- `Server: namecheap-nginx`
- IP like `192.64.119.x` (not your VPS IP)

then **traffic never reaches your VPS**. Nginx and Certbot on the server cannot work until DNS is fixed.

## Fix in Namecheap

1. Log in to [Namecheap](https://www.namecheap.com/) → **Domain List** → **Manage** for `worldcupytu.org`
2. **Remove URL Redirect / URL Forward / Parking** (any forwarding to another URL)
3. Open **Advanced DNS**
4. Set records (replace `YOUR_VPS_IP` with your server IP, e.g. from `curl -4 ifconfig.me` on the VPS):

| Type | Host | Value |
|------|------|--------|
| A Record | `@` | `YOUR_VPS_IP` |
| A Record | `www` | `YOUR_VPS_IP` |

(Or `www` → CNAME → `worldcupytu.org`)

Your VPS IP for `maltamentor.com` is **217.76.52.205** — use the same IP for `worldcupytu.org` and `www`.

**Remove** any **URL Redirect** record that sends traffic to Namecheap (`192.64.119.x` or `X-Served-By: Namecheap URL Forward`).

5. Delete conflicting **URL Redirect** / **Parking** records
6. TTL: Automatic or 5 min for faster propagation

## Verify (from your laptop or VPS)

```bash
dig +short worldcupytu.org
dig +short www.worldcupytu.org
```

Both must show **your VPS IP**, not `192.64.119.x`.

```bash
curl -sI http://worldcupytu.org/ | head -5
```

Must **not** show `Namecheap URL Forward`. You should see `Server: nginx` from your VPS.

Only after this, run:

```bash
sudo bash deploy/scripts/install-nginx-site.sh
sudo CERTBOT_EMAIL=you@example.com bash deploy/scripts/enable-ssl.sh
```
