from machine import Pin
import time

PIN_CAPTEUR = 2
FAISCEAU_COUPE_NIVEAU = 1
COOLDOWN_MS = 900

capteur = Pin(PIN_CAPTEUR, Pin.IN, Pin.PULL_UP)


def faisceau_coupe():
    return capteur.value() == FAISCEAU_COUPE_NIVEAU


def envoyer_evenement():
    print("CUT")


etat_avant = faisceau_coupe()
dernier_declenchement = time.ticks_ms() - COOLDOWN_MS

print("PICO READY")
print("Etat initial =", capteur.value())

while True:
    etat_actuel = faisceau_coupe()

    if etat_actuel and not etat_avant:
        maintenant = time.ticks_ms()

        if time.ticks_diff(maintenant, dernier_declenchement) >= COOLDOWN_MS:
            envoyer_evenement()
            dernier_declenchement = maintenant

    etat_avant = etat_actuel
    time.sleep_ms(10)
