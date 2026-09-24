import argparse
import math
import random
import shutil
import subprocess
import sys
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
    "UP": {"label": "AVANT", "annonce": "Devant"},
    "LEFT": {"label": "GAUCHE", "annonce": "Gauche"},
    "RIGHT": {"label": "DROITE", "annonce": "Droite"},
}

DEFAULT_CLEAR_AFTER_MS = 3000
DEFAULT_ANIMATION_MS = 280
DEFAULT_ARROW_SIZE = 620
DEFAULT_BLOCK_COUNT = 0
DEFAULT_MIN_EVENT_INTERVAL_S = 30.0
MIN_ARROW_SIZE = 260
MAX_ARROW_SIZE = 950
ARROW_HEAD_LENGTH_RATIO = 0.38
ARROW_HEAD_WIDTH_RATIO = 0.72
ARROW_SHAFT_WIDTH_RATIO = 0.34
TEXT_FONT_FAMILY = "Arial"
LABEL_FONT_SIZE = 48
STATUS_FONT_SIZE = 14
CONTROL_BG = "white"
CONTROL_FG = "black"
CONTROL_ACTIVE_BG = "#e6e6e6"
KEY_REPEAT_GUARD_MS = 160
PYSERIAL_MESSAGE = (
    "pyserial non installe. Installer avec : python -m pip install pyserial"
)
PREFERRED_PORT_KEYWORDS = (
    "pico",
    "rp2",
    "micropython",
    "usb serial",
    "usbmodem",
    "usbserial",
    "ttyacm",
)
SYSTEM_PORT_KEYWORDS = (
    "bluetooth",
    "debug-console",
)
SCRIPT_SYNTHESE_WINDOWS = (
    "Add-Type -AssemblyName System.Speech; "
    "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$voixFrancaise = $synth.GetInstalledVoices() | "
    "Where-Object { $_.VoiceInfo.Culture.Name -like 'fr-*' } | "
    "Select-Object -First 1; "
    "if ($null -ne $voixFrancaise) { "
    "$synth.SelectVoice($voixFrancaise.VoiceInfo.Name) }; "
    "$synth.Speak($args[0]); "
    "$synth.Dispose()"
)


def trouver_port_auto():
    if list_ports is None:
        return None

    ports = lister_ports_disponibles()

    if not ports:
        return None

    for port in ports:
        if port_est_utile(port):
            return port["device"]

    if len(ports) == 1:
        return ports[0]["device"]

    return None


def texte_port(port):
    return f"{port['device']} {port['description']} {port['manufacturer']}".lower()


def port_est_systeme(port):
    texte = texte_port(port)
    return any(mot in texte for mot in SYSTEM_PORT_KEYWORDS)


def port_est_utile(port):
    texte = texte_port(port)
    return any(mot in texte for mot in PREFERRED_PORT_KEYWORDS)


def lister_ports_disponibles(inclure_systeme=False):
    if list_ports is None:
        return []

    ports = [
        {
            "device": port.device,
            "description": port.description or "",
            "manufacturer": port.manufacturer or "",
        }
        for port in list_ports.comports()
    ]

    if inclure_systeme:
        return ports

    ports_utiles = [port for port in ports if port_est_utile(port)]
    if ports_utiles:
        return ports_utiles

    return [port for port in ports if not port_est_systeme(port)]


def secondes_non_negatives(valeur):
    try:
        secondes = float(valeur)
    except ValueError as erreur:
        raise argparse.ArgumentTypeError(
            "la valeur doit etre un nombre de secondes"
        ) from erreur

    if not math.isfinite(secondes) or secondes < 0:
        raise argparse.ArgumentTypeError(
            "la valeur doit etre un nombre fini, positif ou nul"
        )

    return secondes


def commande_synthese_vocale(texte):
    if sys.platform == "darwin":
        commande_say = shutil.which("say")
        if commande_say is not None:
            return [commande_say, texte]
    elif sys.platform == "win32":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell is not None:
            return [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                SCRIPT_SYNTHESE_WINDOWS,
                texte,
            ]

    return None


def prononcer(texte):
    commande = commande_synthese_vocale(texte)
    if commande is None:
        return

    try:
        subprocess.run(
            commande,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


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

                    if not message:
                        continue

                    file_messages.put(("SERIAL", message))

                    if "CUT" in message:
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
    def __init__(
        self,
        root,
        port,
        baudrate,
        clear_after_ms,
        animation_ms,
        arrow_size,
        min_event_interval_s,
        fullscreen,
    ):
        self.root = root
        self.port = port
        self.baudrate = baudrate
        self.clear_after_ms = clear_after_ms
        self.animation_ms = animation_ms
        self.min_event_interval_s = min_event_interval_s
        taille_initiale = max(MIN_ARROW_SIZE, min(MAX_ARROW_SIZE, arrow_size))

        self.file_messages = Queue()
        self.arret = threading.Event()
        self.lecture_arret = None
        self.thread = None
        self.clear_job = None
        self.animation_jobs = []
        self.last_manual_trigger = 0.0
        self.last_event_at = None
        self.current_direction = None
        self.current_arrow_size = taille_initiale
        self.current_arrow_color = "white"
        self.arrow_size_var = tk.IntVar(value=taille_initiale)
        self.afficher_tous_ports = False
        self.cut_count = 0
        self.block_sequence = []
        self.block_total = 0
        self.block_count_vars = {
            "RIGHT": tk.IntVar(value=DEFAULT_BLOCK_COUNT),
            "LEFT": tk.IntVar(value=DEFAULT_BLOCK_COUNT),
            "UP": tk.IntVar(value=DEFAULT_BLOCK_COUNT),
        }

        self.root.title("Directions aleatoires")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", fullscreen)
        self.root.bind_all("<Escape>", self.quitter)
        self.root.bind_all("q", self.quitter)

        # Test manuel : barre espace = simuler une coupure du faisceau.
        self.root.bind_all("<space>", self.declencher_manuellement)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.arrow_canvas = tk.Canvas(
            root,
            bg="black",
            highlightthickness=0,
        )
        self.arrow_canvas.grid(row=0, column=0, sticky="nsew")
        self.arrow_canvas.bind("<Configure>", lambda event: self.redessiner_fleche())

        self.text_label = tk.Label(
            root,
            text="PRET",
            font=(TEXT_FONT_FAMILY, LABEL_FONT_SIZE, "bold"),
            fg="white",
            bg="black",
        )
        self.text_label.grid(row=1, column=0, pady=(0, 4), sticky="ew")

        self.size_slider = tk.Scale(
            root,
            from_=MIN_ARROW_SIZE,
            to=MAX_ARROW_SIZE,
            orient="horizontal",
            variable=self.arrow_size_var,
            command=self.modifier_taille_fleche,
            showvalue=True,
            resolution=10,
            length=520,
            bg="black",
            fg="white",
            troughcolor="#222222",
            highlightthickness=0,
        )
        self.size_slider.grid(row=2, column=0, pady=(0, 4))
        self.size_slider.bind("<space>", self.declencher_manuellement)

        self.block_frame = tk.Frame(root, bg="black")
        self.block_frame.grid(row=3, column=0, pady=(0, 4))

        self.block_title = tk.Label(
            self.block_frame,
            text="Bloc",
            font=("Arial", STATUS_FONT_SIZE),
            fg="white",
            bg="black",
        )
        self.block_title.pack(side="left", padx=(0, 8))

        self.right_count_spinbox = self.creer_spinbox_bloc("Droite", "RIGHT")
        self.left_count_spinbox = self.creer_spinbox_bloc("Gauche", "LEFT")
        self.up_count_spinbox = self.creer_spinbox_bloc("Tout droit", "UP")

        self.block_button = tk.Button(
            self.block_frame,
            text="Generer bloc",
            command=self.generer_bloc,
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            activebackground=CONTROL_ACTIVE_BG,
            activeforeground=CONTROL_FG,
            highlightthickness=0,
        )
        self.block_button.pack(side="left", padx=(8, 0))

        self.clear_block_button = tk.Button(
            self.block_frame,
            text="Vider",
            command=self.vider_bloc,
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            activebackground=CONTROL_ACTIVE_BG,
            activeforeground=CONTROL_FG,
            highlightthickness=0,
        )
        self.clear_block_button.pack(side="left", padx=(8, 0))

        self.block_status_label = tk.Label(
            self.block_frame,
            text="Bloc vide : aleatoire simple",
            font=("Arial", STATUS_FONT_SIZE),
            fg="gray",
            bg="black",
        )
        self.block_status_label.pack(side="left", padx=(12, 0))

        self.port_frame = tk.Frame(root, bg="black")
        self.port_frame.grid(row=4, column=0, pady=(0, 4))

        self.selected_port_var = tk.StringVar(value="")
        self.port_label = tk.Label(
            self.port_frame,
            text="Port USB/serie",
            font=("Arial", STATUS_FONT_SIZE),
            fg="white",
            bg="black",
        )
        self.port_label.pack(side="left", padx=(0, 8))

        self.port_menu = tk.OptionMenu(self.port_frame, self.selected_port_var, "")
        self.port_menu.config(
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            activebackground=CONTROL_ACTIVE_BG,
            activeforeground=CONTROL_FG,
            highlightthickness=0,
            width=24,
        )
        self.port_menu["menu"].config(bg=CONTROL_BG, fg=CONTROL_FG)
        self.port_menu.pack(side="left", padx=(0, 8))

        self.refresh_button = tk.Button(
            self.port_frame,
            text="Rafraichir",
            command=self.actualiser_ports,
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            activebackground=CONTROL_ACTIVE_BG,
            activeforeground=CONTROL_FG,
            highlightthickness=0,
        )
        self.refresh_button.pack(side="left", padx=(0, 8))

        self.connect_button = tk.Button(
            self.port_frame,
            text="Connecter",
            command=self.connecter_port_selectionne,
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            activebackground=CONTROL_ACTIVE_BG,
            activeforeground=CONTROL_FG,
            highlightthickness=0,
        )
        self.connect_button.pack(side="left")

        self.all_ports_button = tk.Button(
            self.port_frame,
            text="Tous les ports",
            command=self.basculer_affichage_ports,
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            activebackground=CONTROL_ACTIVE_BG,
            activeforeground=CONTROL_FG,
            highlightthickness=0,
        )
        self.all_ports_button.pack(side="left", padx=(8, 0))

        self.status_label = tk.Label(
            root,
            text="Echap ou q pour quitter. Barre espace = declencher une animation.",
            font=("Arial", STATUS_FONT_SIZE),
            fg="gray",
            bg="black",
        )
        self.status_label.grid(row=5, column=0, pady=(0, 8), sticky="ew")

        self.serial_debug_label = tk.Label(
            root,
            text="Serie : aucune ligne recue | CUT recus : 0",
            font=("Arial", STATUS_FONT_SIZE),
            fg="gray",
            bg="black",
        )
        self.serial_debug_label.grid(row=6, column=0, pady=(0, 8), sticky="ew")

        if serial is None:
            self.status_label.config(text=f"{PYSERIAL_MESSAGE}. Espace = test.")
            self.refresh_button.config(state="disabled")
            self.connect_button.config(state="disabled")
            self.port_menu.config(state="disabled")
            self.all_ports_button.config(state="disabled")
        else:
            self.actualiser_ports(selection=self.port)
            if self.port is None:
                self.status_label.config(text="Aucun port serie detecte.")
            else:
                self.connecter_port(self.port)

        self.root.after(50, self.traiter_messages)

    def afficher_pret(self):
        self.annuler_animation()
        self.current_direction = None
        self.arrow_canvas.delete("all")
        self.text_label.config(text="PRET", fg="white")
        self.clear_job = None

    def afficher_direction(self, direction):
        self.annuler_animation()
        data = DIRECTIONS[direction]
        self.current_direction = direction
        self.current_arrow_size = self.arrow_size_var.get()
        self.current_arrow_color = "white"
        self.redessiner_fleche()
        self.text_label.config(text=data["label"])
        threading.Thread(
            target=prononcer,
            args=(data["annonce"],),
            daemon=True,
        ).start()
        self.lancer_animation()

        if self.clear_job is not None:
            self.root.after_cancel(self.clear_job)
            self.clear_job = None

        if self.clear_after_ms > 0:
            self.clear_job = self.root.after(self.clear_after_ms, self.afficher_pret)

    def afficher_direction_aleatoire(self):
        direction = self.prochaine_direction()
        self.afficher_direction(direction)

    def declencher_evenement(self, direction=None):
        maintenant = time.monotonic()

        if self.last_event_at is not None:
            ecoule = maintenant - self.last_event_at
            if ecoule < self.min_event_interval_s:
                attente = self.min_event_interval_s - ecoule
                self.status_label.config(
                    text=f"Evenement ignore : attendre encore {attente:.1f} s."
                )
                return False

        self.last_event_at = maintenant
        if direction is None:
            self.afficher_direction_aleatoire()
        else:
            self.afficher_direction(direction)

        return True

    def declencher_manuellement(self, event=None):
        maintenant = time.monotonic()
        if maintenant - self.last_manual_trigger < KEY_REPEAT_GUARD_MS / 1000:
            return "break"

        self.last_manual_trigger = maintenant
        self.file_messages.put(("TRIGGER", "clavier"))
        return "break"

    def creer_spinbox_bloc(self, texte, direction):
        label = tk.Label(
            self.block_frame,
            text=texte,
            font=("Arial", STATUS_FONT_SIZE),
            fg="white",
            bg="black",
        )
        label.pack(side="left", padx=(0, 4))

        spinbox = tk.Spinbox(
            self.block_frame,
            from_=0,
            to=999,
            width=4,
            textvariable=self.block_count_vars[direction],
            bg=CONTROL_BG,
            fg=CONTROL_FG,
            buttonbackground=CONTROL_ACTIVE_BG,
            highlightthickness=0,
        )
        spinbox.pack(side="left", padx=(0, 8))
        spinbox.bind("<space>", self.declencher_manuellement)
        return spinbox

    def lire_compte_bloc(self, direction):
        try:
            return max(0, int(self.block_count_vars[direction].get()))
        except (tk.TclError, ValueError):
            self.block_count_vars[direction].set(0)
            return 0

    def generer_bloc(self):
        sequence = []
        for direction in ("RIGHT", "LEFT", "UP"):
            sequence.extend([direction] * self.lire_compte_bloc(direction))

        random.shuffle(sequence)
        self.block_sequence = sequence
        self.block_total = len(sequence)
        self.mettre_a_jour_statut_bloc()

    def vider_bloc(self):
        self.block_sequence = []
        self.block_total = 0
        self.mettre_a_jour_statut_bloc()

    def prochaine_direction(self):
        if self.block_sequence:
            direction = self.block_sequence.pop(0)
            self.mettre_a_jour_statut_bloc()
            return direction

        return random.choice(list(DIRECTIONS.keys()))

    def mettre_a_jour_statut_bloc(self):
        restant = len(self.block_sequence)
        if self.block_total == 0:
            self.block_status_label.config(text="Bloc vide : aleatoire simple")
        elif restant == 0:
            self.block_status_label.config(text="Bloc termine : aleatoire simple")
        else:
            self.block_status_label.config(
                text=f"Bloc : {restant}/{self.block_total} restants"
            )

    def actualiser_ports(self, selection=None):
        ports = lister_ports_disponibles(inclure_systeme=self.afficher_tous_ports)
        devices = [port["device"] for port in ports]

        if selection is not None and selection not in devices:
            devices.insert(0, selection)

        menu = self.port_menu["menu"]
        menu.delete(0, "end")

        if not devices:
            self.selected_port_var.set("")
            menu.add_command(label="Aucun port", command=lambda: None)
            self.connect_button.config(state="disabled")
            if self.afficher_tous_ports:
                self.status_label.config(text="Aucun port serie detecte.")
            else:
                self.status_label.config(
                    text=(
                        "Aucun Pico/USB serie detecte. Branche le Pico, "
                        "puis clique Rafraichir."
                    )
                )
            return

        for device in devices:
            menu.add_command(
                label=device,
                command=lambda device=device: self.selected_port_var.set(device),
            )

        self.connect_button.config(state="normal")
        if selection in devices:
            self.selected_port_var.set(selection)
        elif self.selected_port_var.get() not in devices:
            self.selected_port_var.set(devices[0])

        if self.afficher_tous_ports:
            self.status_label.config(text="Tous les ports sont affiches.")
        elif self.port is None:
            self.status_label.config(text="Port USB serie detecte.")

    def basculer_affichage_ports(self):
        self.afficher_tous_ports = not self.afficher_tous_ports
        if self.afficher_tous_ports:
            self.all_ports_button.config(text="Ports utiles")
        else:
            self.all_ports_button.config(text="Tous les ports")

        self.actualiser_ports(selection=self.port)

    def connecter_port_selectionne(self):
        port = self.selected_port_var.get()
        if not port:
            self.status_label.config(text="Aucun port serie selectionne.")
            return

        self.connecter_port(port)

    def connecter_port(self, port):
        if serial is None:
            self.status_label.config(text=f"{PYSERIAL_MESSAGE}. Espace = test.")
            return

        if self.thread is not None and self.thread.is_alive() and self.port == port:
            self.status_label.config(text=f"Deja connecte : {port}")
            return

        self.arreter_lecture_serie()
        self.port = port
        self.lecture_arret = threading.Event()
        self.thread = threading.Thread(
            target=lecteur_serie,
            args=(port, self.baudrate, self.file_messages, self.lecture_arret),
            daemon=True,
        )
        self.thread.start()
        self.status_label.config(text=f"Connexion : {port}")

    def arreter_lecture_serie(self):
        if self.lecture_arret is not None:
            self.lecture_arret.set()
            self.lecture_arret = None

    def modifier_taille_fleche(self, valeur):
        if self.current_direction is None:
            return

        self.current_arrow_size = int(float(valeur))
        self.redessiner_fleche()

    def redessiner_fleche(self):
        self.arrow_canvas.delete("all")

        if self.current_direction is None:
            return

        largeur = max(self.arrow_canvas.winfo_width(), 1)
        hauteur = max(self.arrow_canvas.winfo_height(), 1)
        taille = min(self.current_arrow_size, int(largeur * 0.92), int(hauteur * 0.92))
        points = self.points_fleche(
            self.current_direction, taille, largeur / 2, hauteur / 2
        )
        self.arrow_canvas.create_polygon(
            points,
            fill=self.current_arrow_color,
            outline=self.current_arrow_color,
        )

    def points_fleche(self, direction, taille, centre_x, centre_y):
        demi = taille / 2
        tete = taille * ARROW_HEAD_LENGTH_RATIO
        largeur_tete = taille * ARROW_HEAD_WIDTH_RATIO
        largeur_corps = taille * ARROW_SHAFT_WIDTH_RATIO
        base_tete = demi - tete

        points = [
            (-demi, -largeur_corps / 2),
            (base_tete, -largeur_corps / 2),
            (base_tete, -largeur_tete / 2),
            (demi, 0),
            (base_tete, largeur_tete / 2),
            (base_tete, largeur_corps / 2),
            (-demi, largeur_corps / 2),
        ]

        if direction == "LEFT":
            points = [(-x, y) for x, y in points]
        elif direction == "UP":
            points = [(y, -x) for x, y in points]

        return [
            coord
            for x, y in points
            for coord in (centre_x + x, centre_y + y)
        ]

    def lancer_animation(self):
        if self.animation_ms <= 0:
            return

        taille_base = self.arrow_size_var.get()
        etapes = [
            (0.0, max(MIN_ARROW_SIZE, int(taille_base * 0.86)), "#7dd3fc"),
            (0.18, min(MAX_ARROW_SIZE, int(taille_base * 1.12)), "white"),
            (0.42, max(MIN_ARROW_SIZE, int(taille_base * 0.95)), "#f8fafc"),
            (0.70, min(MAX_ARROW_SIZE, int(taille_base * 1.06)), "white"),
            (1.0, taille_base, "white"),
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
        self.current_arrow_size = taille
        self.current_arrow_color = couleur
        self.redessiner_fleche()
        self.text_label.config(fg=couleur)

    def annuler_animation(self):
        for job in self.animation_jobs:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

        self.animation_jobs.clear()
        self.current_arrow_size = self.arrow_size_var.get()
        self.current_arrow_color = "white"
        self.redessiner_fleche()
        self.text_label.config(fg="white")

    def traiter_messages(self):
        try:
            while True:
                type_message, contenu = self.file_messages.get_nowait()

                if type_message == "STATUS":
                    self.status_label.config(text=contenu)
                elif type_message == "SERIAL":
                    self.serial_debug_label.config(
                        text=f"Serie : {contenu} | CUT recus : {self.cut_count}"
                    )
                elif type_message == "TRIGGER":
                    if contenu == "capteur":
                        self.cut_count += 1
                        self.serial_debug_label.config(
                            text=f"Serie : CUT | CUT recus : {self.cut_count}"
                        )
                    self.declencher_evenement()
                elif type_message == "DIRECTION":
                    self.declencher_evenement(contenu)

        except Empty:
            pass

        self.root.after(50, self.traiter_messages)

    def quitter(self, event=None):
        self.arret.set()
        self.arreter_lecture_serie()
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
        "--arrow-size",
        type=int,
        default=DEFAULT_ARROW_SIZE,
        help="Taille initiale de la fleche. Ajustable ensuite avec le slider.",
    )
    parser.add_argument(
        "--min-event-interval-s",
        type=secondes_non_negatives,
        default=DEFAULT_MIN_EVENT_INTERVAL_S,
        help=(
            "Delai minimal entre deux evenements en secondes "
            f"(defaut : {DEFAULT_MIN_EVENT_INTERVAL_S:g}). 0 desactive la limite."
        ),
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
        args.arrow_size,
        args.min_event_interval_s,
        fullscreen=not args.windowed,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
