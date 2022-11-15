#!/usr/bin/env python3

"""Eco PLC gateway: a modbus server that relay data from french energy network operators websites to a PLC device

Modbus map for ecogaz signal (https://myecogaz.com/)
----------------------------------------------------

    * holding registers space (readable with modbus function 3)

        @0  ecogaz current day color
        @1  ecogaz 1 day ahead color
        @2  ecogaz 2 days ahead color
        @3  ecogaz 3 days ahead color
        @4  ecogaz 4 days ahead color
        @5  ecogaz 5 days ahead color
        color register encoding is 0 = data not available, 1 = green, 2 = yellow, 3 = orange, 4 = red
        more details at https://odre.opendatasoft.com/explore/dataset/signal-ecogaz/information/


Modbus map for ecowatt signal (https://monecowatt.fr/)
------------------------------------------------------

    * holding registers space (readable with modbus function 3)

        @100  ecowatt current day color
        @101  ecowatt 1 day ahead color
        @102  ecowatt 2 days ahead color
        @103  ecowatt 3 days ahead color
        color register encoding is 0 = data not available, 1 = green, 2 = orange, 3 = red
        more details at https://data.rte-france.com/catalog/-/api/doc/user-guide/Ecowatt/4.0
"""

import argparse
import base64
from datetime import datetime as dt
from datetime import timedelta
import logging
from threading import Lock
import time
import json
from urllib.error import URLError
from urllib.request import urlopen, Request
# for ecowatt job: create an account on https://data.rte-france.com/
# create an app (give you client and secret ids) and link it to ecowatt API endpoint
from private_data import RTE_CLIENT_ID, RTE_SECRET_ID
# sudo apt install python3-dateutil python3-tz
from dateutil.parser import parse as dt_parse
import pytz
# sudo pip3 install 'pyModbusTCP>=0.2.0'
from pyModbusTCP.server import ModbusServer, DataBank


# some class
class Share:
    """A container to share modbus registers."""
    lock = Lock()
    v_hold_regs_d = {0: 0, 1: 0, 2: 0, 3: 4, 4: 5, 5: 0, 100: 0, 101: 0, 102: 0, 103: 0}


class MyDataBank(DataBank):
    """A custom ModbusServerDataBank for override get_holding_registers method."""

    def __init__(self):
        # turn off allocation of memory for standard modbus object types
        # only "holding registers" space will be replaced by dynamic build values.
        super().__init__(virtual_mode=True)

    def get_holding_registers(self, address, number=1, srv_info=None):
        """Get virtual holding registers."""
        # build a list of virtual regs to return to server data handler
        # return None if any of virtual registers is missing
        try:
            with Share.lock:
                return [Share.v_hold_regs_d[a] for a in range(address, address + number)]
        except KeyError:
            return


# define jobs
class Job:
    """Job skeleton."""

    def __init__(self, every_s: int, runnable_now: bool = False, enable: bool = True) -> None:
        # public
        self.enable = enable
        self.every_s = every_s
        # private
        self._last_run_t = float('-inf') if runnable_now else time.monotonic()

    def update(self):
        """Check if the run method should be executed and do-it."""
        # job is runnable ?
        if self.enable and (time.monotonic() - self._last_run_t) > self.every_s:
            logging.info(f'run {type(self).__name__}')
            self._last_run_t = time.monotonic()
            self.run()

    def run(self):
        """Main job code this method must be overridden on the child."""
        pass


class DebugJob(Job):
    """Debug task(s) job."""

    def run(self):
        with Share.lock:
            logging.debug(f'Share.v_hold_regs_d={Share.v_hold_regs_d}')


class EcogazJob(Job):
    """Retrieve ecogaz-signal data job."""
    # const
    API_URL = 'https://odre.opendatasoft.com/api/v2/catalog/datasets/signal-ecogaz/exports/' \
              'json?select=gas_day,color,indice_de_couleur&order_by=gas_day%20desc&limit=7'

    def run(self):
        # HTTP request and data parse with errors handling
        odre_js_d = {}
        try:
            # request
            r = urlopen(self.API_URL)
            # decode json message
            odre_js_d_l = json.loads(r.read())
            # convert data to dict with keys as python date
            for odre_day_d in odre_js_d_l:
                odre_js_d[dt_parse(odre_day_d['gas_day']).date()] = int(odre_day_d['indice_de_couleur'])
        except URLError as e:
            logging.warning(f'network error in {type(self).__name__}: {e!r}')
        except (json.decoder.JSONDecodeError, ValueError) as e:
            logging.warning(f'wrong data format in {type(self).__name__}: {e!r}')
        # create a date dict with 5 days ahead and populate it with data from ODRE json
        daily_d = {}
        today_dt = dt.now(tz=pytz.timezone('Europe/Paris')).date()
        for d_offset in range(6):
            day_date = today_dt + timedelta(days=d_offset)
            daily_d[day_date] = odre_js_d.get(day_date, 0)
        # update modbus holding registers
        with Share.lock:
            for d_idx, date in enumerate(sorted(daily_d.keys())):
                Share.v_hold_regs_d[d_idx] = daily_d.get(date)


class EcowattJob(Job):
    """Retrieve ecowatt-signal data job."""
    # const
    AUTH_SRV_URL = 'https://digital.iservices.rte-france.com/token/oauth/'
    RES_SRV_URL = 'https://digital.iservices.rte-france.com/open_api/ecowatt/v4/signals'

    def run(self):
        # HTTP request and data parse with errors handling
        fmt_js_d = {}
        try:
            # 1st step: retrieve an access token from authorization server
            auth_str = base64.b64encode(f'{RTE_CLIENT_ID}:{RTE_SECRET_ID}'.encode()).decode()
            headers_d = {'authorization': f'Basic {auth_str}', 'content-type': 'application/x-www-form-urlencoded'}
            http_resp = urlopen(Request(self.AUTH_SRV_URL, headers=headers_d, data=b''))
            # decode json response
            data_d = json.loads(http_resp.read())
            token_value = data_d['access_token']
            # token_expires_s = data_d['expires_in']
            # token_type = data_d['token_type']
            # 2nd step: retrieve ecowatt signal from resource server with the access token in request headers
            http_resp = urlopen(Request(self.RES_SRV_URL, headers={'authorization': f'Bearer {token_value}'}))
            # decode and show json data
            raw_js_d = json.loads(http_resp.read())
            # convert data to dict with keys as python date
            for sig_day_d in raw_js_d['signals']:
                fmt_js_d[dt_parse(sig_day_d['jour']).date()] = dict(value=int(sig_day_d['dvalue']),
                                                                    message=sig_day_d['message'])
        except URLError as e:
            logging.warning(f'network error in {type(self).__name__}: {e!r}')
        except (json.decoder.JSONDecodeError, ValueError, KeyError) as e:
            logging.warning(f'wrong data format in {type(self).__name__}: {e!r}')
        # create a date dict with 3 days ahead and populate it with data from RTE json
        daily_d = {}
        today_dt = dt.now(tz=pytz.timezone('Europe/Paris')).date()
        for offset in range(4):
            day_date = today_dt + timedelta(days=offset)
            daily_d[day_date] = fmt_js_d.get(day_date, dict(value=0, message=''))
        # update modbus holding registers
        with Share.lock:
            for d_idx, date in enumerate(sorted(daily_d.keys())):
                Share.v_hold_regs_d[100 + d_idx] = daily_d[date]['value']


if __name__ == '__main__':
    # parse args
    parser = argparse.ArgumentParser()
    parser.add_argument('-H', '--host', type=str, default='localhost', help='Host (default: localhost)')
    parser.add_argument('-p', '--port', type=int, default=502, help='TCP port (default: 502)')
    parser.add_argument('-d', '--debug', action='store_true', default=False, help='debug mode')
    args = parser.parse_args()
    # logging setup
    lvl = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=lvl)
    logging.info('eco-plc-gw started')
    # init modbus server and start it
    logging.info(f'start modbus server at {args.host}:{args.port}')
    server = ModbusServer(host=args.host, port=args.port, no_block=True, data_bank=MyDataBank())
    server.start()
    # init jobs
    ecogaz_job = EcogazJob(every_s=3600, runnable_now=True)
    ecowatt_job = EcowattJob(every_s=3600, runnable_now=True)
    debug_job = DebugJob(every_s=5, runnable_now=True, enable=args.debug)
    jobs_scheduler_d = dict(ecogaz=ecogaz_job, ecowatt=ecowatt_job, debug=debug_job)
    # jobs update loop
    while True:
        # jobs scheduler processing
        for name, job in jobs_scheduler_d.items():
            job.update()
        # wait next loop
        time.sleep(1.0)
