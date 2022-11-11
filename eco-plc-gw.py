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

        -> currently it's a work in progress

"""

import argparse
from datetime import datetime as dt
from datetime import timedelta
import logging
from threading import Lock
import time
import json
from urllib.error import URLError
from urllib.request import urlopen
# sudo apt install python3-dateutil python3-tz
from dateutil.parser import parse as dt_parse
import pytz
# sudo pip3 install 'pyModbusTCP>=0.2.0'
from pyModbusTCP.server import ModbusServer, DataBank


# some class
class Share:
    lock = Lock()
    v_hold_regs_d = {}


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
                return [Share.v_hold_regs_d[a] for a in range(address, address+number)]
        except KeyError:
            return


# define jobs
class Job:
    def __init__(self, every_s: int, runnable_now: bool = False, enable: bool = True) -> None:
        # public
        self.enable = enable
        self.every_s = every_s
        # private
        self._last_run_t = float('-inf') if runnable_now else time.monotonic()
    
    def update(self):
        # job is runnable ?
        if self.enable and (time.monotonic() - self._last_run_t) > self.every_s:
            logging.info(f'run {type(self).__name__}')
            self._last_run_t = time.monotonic()
            self.run()

    def run(self):
        pass


class DebugJob(Job):
    def run(self):
        with Share.lock:
            logging.debug(f'{Share.v_hold_regs_d=}')


class EcogazJob(Job):
    # const
    API_URL = 'https://odre.opendatasoft.com/api/v2/catalog/datasets/signal-ecogaz/exports/' \
              'json?select=gas_day,color,indice_de_couleur&order_by=gas_day%20desc&limit=7'

    def run(self):
        # HTTP request and data parse with errors handling
        days_d = {}
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
        today_dt = dt.now(tz=pytz.timezone('Europe/Paris')).date()
        for d_offset in range(6):
            day_date = today_dt + timedelta(days=d_offset)
            days_d[day_date] = odre_js_d.get(day_date, 0)
        # update modbus holding registers
        with Share.lock:
            for d_idx, date in enumerate(sorted(days_d.keys())):
                Share.v_hold_regs_d[d_idx] = days_d[date]


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
    debug_job = DebugJob(every_s=5, runnable_now=True, enable=args.debug)
    jobs_scheduler_d = dict(ecogaz=ecogaz_job, debug=debug_job)
    # jobs update loop
    while True:
        # jobs scheduler processing
        for name, job in jobs_scheduler_d.items():
            job.update()
        # wait next loop
        time.sleep(1.0)
