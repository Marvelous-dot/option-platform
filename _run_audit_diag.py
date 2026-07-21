import urllib.request, json, sys
try:
    req = urllib.request.Request('http://localhost:8000/api/state', headers={'User-Agent': 'audit'})
    r = urllib.request.urlopen(req, timeout=5)
    data = json.loads(r.read().decode())
    targets = data.get('targets', [])
    print(f"STATE_OK|{len(targets)}")
    for t in targets:
        code = t.get('target', '?')
        name = t.get('target_name', '?')
        price = t.get('latest_price', 0)
        contracts = t.get('contracts', [])
        print(f"TARGET|{code}|{name}|{price}|{len(contracts)}")
        for c in contracts:
            oc = c.get('option_code', '?')
            delta = c.get('delta')
            iv = c.get('implied_volatility')
            exp = c.get('expiry_date', '')
            otype = c.get('option_type', '?')
            tp = c.get('theoretical_price', 0)
            lp = c.get('last_price', 0)
            print(f"  CONTRACT|{oc}|{otype}|delta={delta}|iv={iv}|exp={exp}|tp={tp}|lp={lp}")
except Exception as e:
    print(f"ERR|{e}")
