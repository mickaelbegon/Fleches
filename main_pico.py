"""Raspberry Pi Pico H - MicroPython.

Lit un capteur photoelectrique NPN sur GP2 et envoie "CUT" par USB serie
lorsqu'une nouvelle coupure du faisceau est detectee.
"""

from machine import Pin
import time
import sys

PIN_CAPTEUR = 2
BOUCLE_MS = 10

# A ajuster apres test :
# Mets 1 si la valeur brute vaut 1 quand le faisceau est coupe.
# Mets 0 si la valeur brute vaut 0 quand le faisceau est coupe.
FAISCEAU_COUPE_NIVEAU = 1

# Evite les doubles declenchements si la personne reste dans le faisceau.
COOLDOWN_MS = 900

capteur = Pin(PIN_CAPTEUR, Pin.IN, Pin.PULL_UP)


def faisceau_coupe():
    return capteur.value() == FAISCEAU_COUPE_NIVEAU


def envoyer_evenement():
    sys.stdout.write("CUT\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass


def boucle_principale():
    etat_avant = faisceau_coupe()
    dernier_declenchement = time.ticks_ms() - COOLDOWN_MS

    while True:
        etat_actuel = faisceau_coupe()

        # Declenche seulement au front : non coupe -> coupe.
        if etat_actuel and not etat_avant:
            maintenant = time.ticks_ms()

            if time.ticks_diff(maintenant, dernier_declenchement) >= COOLDOWN_MS:
                envoyer_evenement()
                dernier_declenchement = maintenant

        etat_avant = etat_actuel
        time.sleep_ms(BOUCLE_MS)


boucle_principale()
