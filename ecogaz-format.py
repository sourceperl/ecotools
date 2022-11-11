#!/usr/bin/env python3

"""Basic request to ecogaz API endpoint from ODRE platform with parsing and data formatting.
more at https://myecogaz.com/
"""

from datetime import datetime as dt
from datetime import timedelta
import sys
import json
from urllib.error import URLError
from urllib.request import urlopen
from dateutil.parser import parse as dt_parse
import pytz

# some const
API_URL = 'https://odre.opendatasoft.com/api/v2/catalog/datasets/signal-ecogaz/exports/' \
          'json?select=gas_day,color,indice_de_couleur&order_by=gas_day%20desc&limit=7'

# HTTP request and data parse with errors handling
odre_js_d = {}
try:
    # request
    r = urlopen(API_URL)
    # decode json message
    odre_js_d_l = json.loads(r.read())
    # convert data to dict with keys as python date
    for odre_day_d in odre_js_d_l:
        odre_js_d[dt_parse(odre_day_d['gas_day']).date()] = int(odre_day_d['indice_de_couleur'])
except URLError:
    print('network error', file=sys.stderr)
    exit(1)
except (json.decoder.JSONDecodeError, ValueError):
    print('wrong data format', file=sys.stderr)
    exit(2)

# create a date dict with 5 days ahead and populate it with data from ODRE json
days_d = {}
today_dt = dt.now(tz=pytz.timezone('Europe/Paris')).date()
for d_offset in range(5):
    day_date = today_dt + timedelta(days=d_offset)
    days_d[day_date] = odre_js_d.get(day_date, 0)

# show results
COLOR_INDEX = ['n/a', 'vert', 'jaune', 'orange', 'rouge']
for d_idx, date in enumerate(sorted(days_d.keys())):
    d_str = f'J+{d_idx}' if d_idx else 'J0'
    print(f"{d_str:3} ({date.strftime('%d/%m/%Y')}) couleur: {COLOR_INDEX[days_d[date]]}")
