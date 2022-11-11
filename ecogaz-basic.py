#!/usr/bin/env python3

"""Basic request to ecogaz API endpoint from ODRE platform.
more at https://myecogaz.com/
"""

import sys
from pprint import pprint
import json
from urllib.error import URLError
from urllib.request import urlopen


# some const
API_URL = 'https://odre.opendatasoft.com/api/v2/catalog/datasets/signal-ecogaz/exports/' \
          'json?select=gas_day,color&order_by=gas_day%20desc&limit=7'

# HTTP request with errors handling
try:
    r = urlopen(API_URL)
    pprint(json.loads(r.read()))
except URLError:
    print('network error', file=sys.stderr)
    exit(1)
except json.decoder.JSONDecodeError:
    print('wrong data format', file=sys.stderr)
    exit(2)
