#!/usr/bin/env python3

"""Basic request to ecowatt API endpoint from RTE data platform.
Warn: RTE limit request rate to one every 15 minutes, this script return
      HTTPError 429 in case of non-compliance with this limit.
more at https://www.monecowatt.fr/ and https://data.rte-france.com/
"""

import base64
import sys
from pprint import pprint
import json
from urllib.error import URLError
from urllib.request import urlopen, Request
# create an account on https://data.rte-france.com/
# create an app (give you client and secret ids) and link it to ecowatt API endpoint
from private_data import RTE_CLIENT_ID, RTE_SECRET_ID


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
    data_d = json.loads(http_resp.read())
    pprint(data_d)
except URLError as e:
    print(f'network error: {e!r}', file=sys.stderr)
    exit(1)
except (json.decoder.JSONDecodeError, KeyError) as e:
    print(f'wrong data format: {e!r}', file=sys.stderr)
    exit(2)
