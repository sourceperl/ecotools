#!/usr/bin/env python3

"""Basic request to ecowatt API endpoint from RTE data platform with parsing and data formatting.
Warn: RTE limit request rate to one every 15 minutes, this script return
      HTTPError 429 in case of non-compliance with this limit.
more at https://www.monecowatt.fr/ and https://data.rte-france.com/
"""

import base64
from datetime import datetime as dt
from datetime import timedelta
import sys
import json
from urllib.error import URLError
from urllib.request import urlopen, Request
# create an account on https://data.rte-france.com/
# create an app (give you client and secret ids) and link it to ecowatt API endpoint
from private_data import RTE_CLIENT_ID, RTE_SECRET_ID
# sudo apt install python3-dateutil python3-tz
from dateutil.parser import parse as dt_parse
import pytz


# some const
AUTH_SRV_URL = 'https://digital.iservices.rte-france.com/token/oauth/'
RES_SRV_URL = 'https://digital.iservices.rte-france.com/open_api/ecowatt/v4/signals'
DEV_RES_SRV_URL = 'https://digital.iservices.rte-france.com/open_api/ecowatt/v4/sandbox/signals'

# HTTP request
try:
    # 1st step: retrieve an access token from authorization server
    auth_str = base64.b64encode(f'{RTE_CLIENT_ID}:{RTE_SECRET_ID}'.encode()).decode()
    headers_d = {'authorization': f'Basic {auth_str}', 'content-type': 'application/x-www-form-urlencoded'}
    http_resp = urlopen(Request(AUTH_SRV_URL, headers=headers_d, data=b''))
    # decode json response
    data_d = json.loads(http_resp.read())
    token_value = data_d['access_token']
    token_expires_s = data_d['expires_in']
    token_type = data_d['token_type']
    # 2nd step: retrieve ecowatt signal from resource server with the access token in request headers
    http_resp = urlopen(Request(RES_SRV_URL, headers={'authorization': f'Bearer {token_value}'}))
    # decode and show json data
    raw_js_d = json.loads(http_resp.read())
    # convert data to dict with keys as python date
    fmt_js_d = {}
    for sig_day_d in raw_js_d['signals']:
        fmt_js_d[dt_parse(sig_day_d['jour']).date()] = dict(value=int(sig_day_d['dvalue']),
                                                            message=sig_day_d['message'])
    # create a date dict with 3 days ahead and populate it with data from RTE json
    rte_ecw_d = {}
    today_dt = dt.now(tz=pytz.timezone('Europe/Paris')).date()
    for d_offset in range(4):
        day_date = today_dt + timedelta(days=d_offset)
        rte_ecw_d[day_date] = fmt_js_d.get(day_date, dict(value=0, message=''))
    # show results
    COLOR_INDEX = ['n/a', 'vert', 'orange', 'rouge']
    for d_idx, date in enumerate(sorted(rte_ecw_d.keys())):
        d_str = f'J+{d_idx}' if d_idx else 'J0'
        print(f"{d_str:3} ({date.strftime('%d/%m/%Y')}) "
              f"couleur: {COLOR_INDEX[rte_ecw_d[date].get('value', 0)]}, "
              f"message: \"{rte_ecw_d[date].get('message', '')}\"")
except URLError as e:
    print(f'network error: {e!r}', file=sys.stderr)
    exit(1)
except (json.decoder.JSONDecodeError, KeyError) as e:
    print(f'wrong data format: {e!r}', file=sys.stderr)
    exit(2)
