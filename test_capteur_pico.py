"""Test brut du capteur sur Raspberry Pi Pico H.

Noter la valeur RAW faisceau aligne et faisceau coupe, puis reporter la valeur
correspondant au faisceau coupe dans FAISCEAU_COUPE_NIVEAU de main_pico.py.
"""

from machine import Pin
import time

PIN_CAPTEUR = 2
INTERVALLE_S = 0.3

capteur = Pin(PIN_CAPTEUR, Pin.IN, Pin.PULL_UP)


def main():
    while True:
        print("RAW =", capteur.value())
        time.sleep(INTERVALLE_S)


main()
