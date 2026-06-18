# Fleches aleatoires avec capteur IR et Raspberry Pi Pico H

Ce projet affiche une direction aleatoire en plein ecran sur un laptop quand un
capteur photoelectrique branche a un Raspberry Pi Pico H detecte une coupure de
faisceau.

Architecture :

```text
Capteur photoelectrique -> Raspberry Pi Pico H -> USB serie -> laptop -> fleche animee
```

La barre espace declenche aussi une fleche animee. C'est pratique pour tester
l'affichage sans capteur, et le comportement est le meme que lors d'une coupure
du faisceau.

## Fichiers

- `main_pico.py` : code MicroPython final a copier sur le Pico sous le nom `main.py`.
- `test_capteur_pico.py` : script de test pour lire la valeur brute du capteur.
- `afficher_fleches_laptop.py` : application Python a lancer sur le laptop.

## Installation laptop

Creer et activer l'environnement conda :

```bash
conda env create -f environment.yml
conda activate fleches
```

Ou installer seulement la dependance serie dans un environnement Python existant :

```bash
python -m pip install pyserial
```

Sans `pyserial`, l'application peut quand meme etre lancee pour tester les
animations avec la barre espace, mais elle ne pourra pas lire le Pico.

Lister les ports disponibles :

```bash
python -m serial.tools.list_ports
```

Lancer l'affichage avec detection automatique du port :

```bash
python afficher_fleches_laptop.py
```

Ou fournir le port explicitement :

```bash
python afficher_fleches_laptop.py --port COM3
python afficher_fleches_laptop.py --port /dev/tty.usbmodemXXXX
python afficher_fleches_laptop.py --port /dev/ttyACM0
```

Options utiles :

```bash
python afficher_fleches_laptop.py --windowed
python afficher_fleches_laptop.py --clear-after-ms 0
python afficher_fleches_laptop.py --animation-ms 0
```

- `--windowed` : lance l'application dans une fenetre au lieu du plein ecran.
- `--clear-after-ms` : temps d'affichage avant retour a `PRET`. Mettre `0` pour garder la fleche.
- `--animation-ms` : duree de l'animation. Mettre `0` pour la desactiver.

## Touches

- `Espace` : declenche une nouvelle fleche animee, comme le capteur.
- `Echap` ou `q` : quitter.

## Installation Pico

1. Installer MicroPython sur le Raspberry Pi Pico H.
2. Ouvrir Thonny.
3. Copier et lancer `test_capteur_pico.py`.
4. Noter la valeur `RAW` lorsque le faisceau est aligne et lorsqu'il est coupe.
5. Ajuster `FAISCEAU_COUPE_NIVEAU` dans `main_pico.py`.
6. Copier `main_pico.py` sur le Pico sous le nom `main.py`.
7. Fermer Thonny avant de lancer l'application laptop, sinon le port serie peut rester occupe.

## Protocole serie

Le Pico envoie une ligne `CUT` quand une nouvelle coupure du faisceau est
detectee. L'application laptop accepte aussi `UP`, `LEFT` et `RIGHT` si l'on veut
forcer une direction depuis un autre emetteur serie.

Le baudrate par defaut est `115200`.
