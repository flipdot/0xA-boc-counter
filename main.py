#!/usr/bin/env python3

import http
import http.client
import sys
import json

from gpiozero import Button
from datetime import datetime
from typing import NamedTuple, List
from colorama import Fore, Style

from config import printer, API_HOST, API_PREFIX, DB_SENSOR_TYPE, STATS_URL, PRINTER_CHAR_WIDTH, BANNER_FREQUENCY, QR_CODE_SIZE

banner_counter = 0
current_value_map = {}


def log(message: str = None) -> None:
    if message is None:
        print()
    else:
        print(Style.DIM + '[' + str(datetime.now()) + ']' + Style.RESET_ALL + ' ' + str(message))


class Beverage(NamedTuple):
    id: str
    display_name: str

    def increment_counter(self) -> None:
        last_value = current_value_map[self.id]
        new_value = last_value + 1

        for handler in ORDER_HANDLERS:
            try:
                handler(self, new_value)
            except KeyboardInterrupt:
                sys.exit()
            except Exception as e:
                print(e)
            current_value_map[self.id] = new_value


def publish_order_to_db(beverage: Beverage, new_value: int) -> None:
    res = request('put', API_PREFIX, body=[
        {
            'SensorType': DB_SENSOR_TYPE,
            'Location': beverage.id,
            'Value': new_value,
            'Unit': 'drk',
            'Description': beverage.display_name,
        },
    ])


def print_order_to_stdout(beverage: Beverage, new_value: int) -> None:
    log(f'🍻 {beverage.display_name} (now {new_value})')


def print_order_to_thermal(beverage: Beverage, new_value: int) -> None:
    if printer is None:
        return

    global banner_counter

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    printer.text(timestamp + '\n')
    printer.text(beverage.display_name + ' #'  + str(new_value) +  '\n')
    printer.text('-' * PRINTER_CHAR_WIDTH + '\n')
    if banner_counter == 0:
        printer.qr(STATS_URL, size=QR_CODE_SIZE)

    banner_counter += 1
    banner_counter %= BANNER_FREQUENCY
    printer.flush()


ORDER_HANDLERS = (
    print_order_to_stdout,
    print_order_to_thermal,
    publish_order_to_db,
)

# Pinout: https://gpiozero.readthedocs.io/en/stable/_images/pin_layout.svg
button_mapping = {
    (Button(2), Beverage('club_mate', 'Club Mate')),
    (Button(3), Beverage('mio_mate', 'Mio Mio Mate')),
    (Button(4), Beverage('mio_cola', 'Mio Mio Cola')),
    (Button(17), Beverage('tschunk', 'Tschunk')),
    (Button(27), Beverage('beer', 'Bier')),
    (Button(22), Beverage('water', 'Wasser')),
    (Button(10), Beverage('special_drink', 'Sonderanfertigung')),
}

def request(method: str, path: str, body = None, blocking = True):
    connection = http.client.HTTPConnection(API_HOST, timeout=9001)
    connection.request(
        method.upper(),
        path,
        body=json.dumps(body) if body is not None else None,
        headers={
            'Content-Type':  'application/json',
        },
    )
    if blocking:
        return connection.getresponse()
    return None

def main() -> None:
    log('🚀 Welcome to the BOC counter!')
    log()
    log('🤔 Requesting current beverage data...')
    res = request('get', '/')
    if res.code != 200:
        log('☹️ SpaceAPI returned error')
        log(res.read().decode('utf-8'))
        return

    current_data = json.loads(res.read().decode('utf-8'))
    sensors: List[dict] = current_data['state']['sensors']

    sensors_of_type = sensors.get(DB_SENSOR_TYPE)
    prefix = DB_SENSOR_TYPE + '_'

    if sensors_of_type is not None:
        for sensor in sensors.get(DB_SENSOR_TYPE):
            beverage_id = sensor['name'][len(prefix):]
            current_value_map[beverage_id] = sensor['value']
        else:
            log(f'😉 {DB_SENSOR_TYPE} was not found. Should be created.')

    for _, beverage in button_mapping:
        if beverage.id not in current_value_map:
            current_value_map[beverage.id] = 0

    for button, beverage in button_mapping:
        button.when_pressed = beverage.increment_counter

    log('🤔 Current values:')
    for key, value in current_value_map.items():
        log(f'\t\t{key}: {value}')
    log()

    log('🍻 Waiting for drinks...')
    log('   Press enter to quit')
    input()

if __name__ == '__main__':
    main()
