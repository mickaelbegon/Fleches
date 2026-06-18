import argparse
import random
import threading
import time
import tkinter as tk
from queue import Queue, Empty

try:
    import serial
    from serial.tools import list_ports
except ModuleNotFoundError:
    serial = None
    list_ports = None


DIRECTIONS = {
    "UP": {"arrow": "↑", "label": "AVANT"},
    "LEFT": {"arrow": "←", "label": "GAUCHE"},
    "RIGHT": {"arrow": "→", "label": "DROITE"},
}

DEFAULT_CLEAR_AFTER_MS = 3000
DEFAULT_ANIMATION_MS = 280
ARROW_FONT_FAMILY = "Arial"
ARROW_FONT_MIN = 220
ARROW_FONT_MAX = 290
LABEL_FONT_SIZE = 70
KEY_REPEAT_GUARD_MS = 160
PYSERIAL_MESSAGE = (
    "pyserial non installe. Installer avec : python -m pip install pyserial"
)


def trouver_port_auto():
    if list_ports is None:
        return None

    ports = list(list_ports.comports())

    if not ports:
        return None

    mots_cles = [
        "pico",
        "rp2",
        "micropython",
        "usb serial",
        "ttyacm",
        "usbmodem",
    ]

    for port in ports:
        texte = f"{port.device} {port.description} {port.manufacturer}".lower()
        if any(mot in texte for mot in mots_cles):
            return port.device

    if len(ports) == 1:
        return ports[0].device

    return None


def lecteur_serie(port, baudrate, file_messages, arret):
    if serial is None:
        file_messages.put(("STATUS", PYSERIAL_MESSAGE))
        return

    while not arret.is_set():
        try:
            with serial.Serial(port, baudrate=baudrate, timeout=1) as ser:
                file_messages.put(("STATUS", f"Connecte : {port}"))
                time.sleep(0.5)
                ser.reset_input_buffer()

                while not arret.is_set():
                    ligne = ser.readline()

                    if not ligne:
                        continue

                    message = ligne.decode("utf-8", errors="ignore").strip().upper()

                    if message == "CUT":
                        file_messages.put(("TRIGGER", "capteur"))
                    elif message in DIRECTIONS:
                        file_messages.put(("DIRECTION", message))

        except serial.SerialException as erreur:
            file_messages.put(("STATUS", f"Port serie indisponible : {erreur}"))
            time.sleep(2)

        except Exception as erreur:
            file_messages.put(("STATUS", f"Erreur : {erreur}"))
            time.sleep(2)


class Application:
    def __init__(self, root, port, baudrate, clear_after_ms, animation_ms, fullscreen):
        self.root = root
        self.port = port
        self.baudrate = baudrate
        self.clear_after_ms = clear_after_ms
        self.animation_ms = animation_ms

        self.file_messages = Queue()
        self.arret = threading.Event()
        self.clear_job = None
        self.animation_jobs = []
        self.last_manual_trigger = 0.0

        self.root.title("Directions aleatoires")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", fullscreen)
        self.root.bind_all("<Escape>", self.quitter)
        self.root.bind_all("q", self.quitter)

        # Test manuel : barre espace = simuler une coupure du faisceau.
        self.root.bind_all("<space>", self.declencher_manuellement)

        self.arrow_label = tk.Label(
            root,
            text="",
            font=(ARROW_FONT_FAMILY, ARROW_FONT_MAX, "bold"),
            fg="white",
            bg="black",
        )
        self.arrow_label.pack(expand=True)

        self.text_label = tk.Label(
            root,
            text="PRET",
            font=(ARROW_FONT_FAMILY, LABEL_FONT_SIZE, "bold"),
            fg="white",
            bg="black",
        )
        self.text_label.pack()

        self.status_label = tk.Label(
            root,
            text="Echap ou q pour quitter. Barre espace = declencher une animation.",
            font=("Arial", 18),
            fg="gray",
            bg="black",
        )
        self.status_label.pack(pady=25)

        if serial is None:
            self.status_label.config(text=f"{PYSERIAL_MESSAGE}. Espace = test.")
        elif self.port is None:
            self.status_label.config(
                text="Aucun port serie detecte. Relancer avec --port COMx ou /dev/ttyACM0."
            )
        else:
            self.thread = threading.Thread(
                target=lecteur_serie,
                args=(self.port, self.baudrate, self.file_messages, self.arret),
                daemon=True,
            )
            self.thread.start()

        self.root.after(50, self.traiter_messages)

    def afficher_pret(self):
        self.annuler_animation()
        self.arrow_label.config(text="")
        self.text_label.config(text="PRET", fg="white")
        self.clear_job = None

    def afficher_direction(self, direction):
        self.annuler_animation()
        data = DIRECTIONS[direction]
        self.arrow_label.config(text=data["arrow"])
        self.text_label.config(text=data["label"])
        self.lancer_animation()

        if self.clear_job is not None:
            self.root.after_cancel(self.clear_job)
            self.clear_job = None

        if self.clear_after_ms > 0:
            self.clear_job = self.root.after(self.clear_after_ms, self.afficher_pret)

    def afficher_direction_aleatoire(self):
        direction = random.choice(list(DIRECTIONS.keys()))
        self.afficher_direction(direction)

    def declencher_manuellement(self, event=None):
        maintenant = time.monotonic()
        if maintenant - self.last_manual_trigger < KEY_REPEAT_GUARD_MS / 1000:
            return "break"

        self.last_manual_trigger = maintenant
        self.file_messages.put(("TRIGGER", "clavier"))
        return "break"

    def lancer_animation(self):
        if self.animation_ms <= 0:
            return

        etapes = [
            (0.0, ARROW_FONT_MIN, "#7dd3fc"),
            (0.18, ARROW_FONT_MAX, "white"),
            (0.42, 255, "#f8fafc"),
            (0.70, 272, "white"),
            (1.0, 260, "white"),
        ]

        for ratio, taille, couleur in etapes:
            delai = int(self.animation_ms * ratio)
            job = self.root.after(
                delai,
                lambda taille=taille, couleur=couleur: self.appliquer_animation(
                    taille, couleur
                ),
            )
            self.animation_jobs.append(job)

    def appliquer_animation(self, taille, couleur):
        self.arrow_label.config(font=(ARROW_FONT_FAMILY, taille, "bold"), fg=couleur)
        self.text_label.config(fg=couleur)

    def annuler_animation(self):
        for job in self.animation_jobs:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

        self.animation_jobs.clear()
        self.arrow_label.config(font=(ARROW_FONT_FAMILY, 260, "bold"), fg="white")
        self.text_label.config(fg="white")

    def traiter_messages(self):
        try:
            while True:
                type_message, contenu = self.file_messages.get_nowait()

                if type_message == "STATUS":
                    self.status_label.config(text=contenu)
                elif type_message == "TRIGGER":
                    self.afficher_direction_aleatoire()
                elif type_message == "DIRECTION":
                    self.afficher_direction(contenu)

        except Empty:
            pass

        self.root.after(50, self.traiter_messages)

    def quitter(self, event=None):
        self.arret.set()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Affiche des fleches aleatoires en plein ecran depuis un Pico "
            "ou la barre espace."
        )
    )
    parser.add_argument(
        "--port", default=None, help="Port serie du Pico, ex. COM3 ou /dev/ttyACM0"
    )
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument(
        "--clear-after-ms",
        type=int,
        default=DEFAULT_CLEAR_AFTER_MS,
        help="Duree d'affichage avant retour a PRET. 0 garde la fleche affichee.",
    )
    parser.add_argument(
        "--animation-ms",
        type=int,
        default=DEFAULT_ANIMATION_MS,
        help="Duree de l'animation de declenchement. 0 desactive l'animation.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Lancer dans une fenetre au lieu du plein ecran.",
    )
    args = parser.parse_args()

    port = args.port or trouver_port_auto()

    root = tk.Tk()
    Application(
        root,
        port,
        args.baudrate,
        args.clear_after_ms,
        args.animation_ms,
        fullscreen=not args.windowed,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
