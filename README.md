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
du faisceau. Chaque direction est aussi annoncee vocalement (`Gauche`,
`Devant` ou `Droite`) avec la voix systeme de macOS ou Windows, sans
dependance Python supplementaire.
Sous Windows, une voix francaise installee est privilegiee ; a defaut, la voix
systeme par defaut est utilisee.

## Fichiers

- `main.py` : code MicroPython pret a copier directement sur le Pico.
- `main_pico.py` : version source/commentee du code Pico.
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

Avec le lanceur conda de ce Mac :

```bash
/Users/mickaelbegon/miniconda3/bin/conda run -n fleches python -m serial.tools.list_ports -v
```

Lancer l'affichage avec detection automatique du port :

```bash
python afficher_fleches_laptop.py
```

Sur ce Mac, si `conda` n'est pas dans le `PATH`, utiliser le lanceur :

```bash
./run_mac.command
```

ou la commande explicite :

```bash
/Users/mickaelbegon/miniconda3/bin/conda run -n fleches python afficher_fleches_laptop.py
```

Dans l'application, le menu `Port USB/serie` permet aussi de choisir un port
parmi ceux disponibles. Sur macOS, meme avec un cable USB-C, le Pico apparait
souvent comme `/dev/cu.usbmodem...` ou `/dev/tty.usbmodem...`. Utiliser
`Rafraichir` apres avoir branche le Pico, puis `Connecter`.

Si le Pico fonctionne dans `screen` mais pas dans l'application, fermer `screen`
avant de connecter le port dans l'application. Un seul programme peut lire le
port serie a la fois. Dans `screen`, quitter avec `Ctrl-A`, puis `K`, puis `y`.

L'application affiche aussi `Serie : ... | CUT recus : ...` en bas de l'ecran.
Si `CUT recus` augmente, le Pico communique bien avec l'application.

Les ports macOS comme `/dev/cu.debug-console` ou
`/dev/cu.Bluetooth-Incoming-Port` ne correspondent pas au Pico et sont masques
par defaut. Le bouton `Tous les ports` permet de les afficher pour diagnostiquer
si besoin.

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
python afficher_fleches_laptop.py --arrow-size 700
python afficher_fleches_laptop.py --min-event-interval-s 30
```

- `--windowed` : lance l'application dans une fenetre au lieu du plein ecran.
- `--clear-after-ms` : temps d'affichage avant retour a `PRET`. Mettre `0` pour garder la fleche.
- `--animation-ms` : duree de l'animation. Mettre `0` pour la desactiver.
- `--arrow-size` : taille initiale de la fleche. Un slider permet ensuite de l'ajuster en direct.
- `--min-event-interval-s` : delai minimal entre deux evenements. Sa valeur par defaut est de `30` secondes ; mettre `0` pour ne pas limiter les declenchements.

## Bloc de conditions

Dans la zone `Bloc`, entrer le nombre voulu de conditions discretes :

- `Droite`
- `Gauche`
- `Tout droit`

Cliquer ensuite sur `Generer bloc`. L'application melange ces conditions et les
utilise une par une a chaque declenchement capteur ou barre espace. Le compteur
indique combien de conditions restent dans le bloc. Quand le bloc est vide,
l'application revient a l'aleatoire simple.

Le bouton `Vider` annule le bloc en cours.

## Touches

- `Espace` : declenche une nouvelle fleche animee, comme le capteur.
- `Echap` ou `q` : quitter.

## Installation Pico

1. Installer MicroPython sur le Raspberry Pi Pico H.
2. Ouvrir Thonny.
3. Copier et lancer `test_capteur_pico.py`.
4. Noter la valeur `RAW` lorsque le faisceau est aligne et lorsqu'il est coupe.
5. Ajuster `FAISCEAU_COUPE_NIVEAU` dans `main.py`.
6. Copier `main.py` sur le Pico.
7. Fermer Thonny avant de lancer l'application laptop, sinon le port serie peut rester occupe.

## Protocole serie

Le Pico envoie une ligne `CUT` quand une nouvelle coupure du faisceau est
detectee. L'application laptop accepte aussi `UP`, `LEFT` et `RIGHT` si l'on veut
forcer une direction depuis un autre emetteur serie.

Le baudrate par defaut est `115200`.
