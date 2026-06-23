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
    "UP": {"label": "AVANT"},
    "LEFT": {"label": "GAUCHE"},
    "RIGHT": {"label": "DROITE"},
}

DEFAULT_CLEAR_AFTER_MS = 3000
DEFAULT_ANIMATION_MS = 280
DEFAULT_ARROW_SIZE = 620
MIN_ARROW_SIZE = 260
MAX_ARROW_SIZE = 950
ARROW_HEAD_LENGTH_RATIO = 0.38
ARROW_HEAD_WIDTH_RATIO = 0.72
ARROW_SHAFT_WIDTH_RATIO = 0.34
TEXT_FONT_FAMILY = "Arial"
LABEL_FONT_SIZE = 48
STATUS_FONT_SIZE = 14
KEY_REPEAT_GUARD_MS = 160
PYSERIAL_MESSAGE = (
    "pyserial non installe. Installer avec : python -m pip install pyserial"
)


def trouver_port_auto():
    if list_ports is None:
        return None

    ports = lister_ports_disponibles()

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
        texte = (
            f"{port['device']} {port['description']} {port['manufacturer']}"
        ).lower()
        if any(mot in texte for mot in mots_cles):
            return port["device"]

    if len(ports) == 1:
        return ports[0]["device"]

    return None


def lister_ports_disponibles():
    if list_ports is None:
        return []

    return [
        {
            "device": port.device,
            "description": port.description or "",
            "manufacturer": port.manufacturer or "",
        }
        for port in list_ports.comports()
    ]


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
    def __init__(
        self,
        root,
        port,
        baudrate,
        clear_after_ms,
        animation_ms,
        arrow_size,
        fullscreen,
    ):
        self.root = root
        self.port = port
        self.baudrate = baudrate
        self.clear_after_ms = clear_after_ms
        self.animation_ms = animation_ms
        taille_initiale = max(MIN_ARROW_SIZE, min(MAX_ARROW_SIZE, arrow_size))

        self.file_messages = Queue()
        self.arret = threading.Event()
        self.lecture_arret = None
        self.thread = None
        self.clear_job = None
        self.animation_jobs = []
        self.last_manual_trigger = 0.0
        self.current_direction = None
        self.current_arrow_size = taille_initiale
        self.current_arrow_color = "white"
        self.arrow_size_var = tk.IntVar(value=taille_initiale)

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

        self.port_frame = tk.Frame(root, bg="black")
        self.port_frame.grid(row=3, column=0, pady=(0, 4))

        self.selected_port_var = tk.StringVar(value="")
        self.port_label = tk.Label(
            self.port_frame,
            text="Port serie",
            font=("Arial", STATUS_FONT_SIZE),
            fg="white",
            bg="black",
        )
        self.port_label.pack(side="left", padx=(0, 8))

        self.port_menu = tk.OptionMenu(self.port_frame, self.selected_port_var, "")
        self.port_menu.config(
            bg="#111111",
            fg="white",
            activebackground="#222222",
            activeforeground="white",
            highlightthickness=0,
            width=24,
        )
        self.port_menu["menu"].config(bg="#111111", fg="white")
        self.port_menu.pack(side="left", padx=(0, 8))

        self.refresh_button = tk.Button(
            self.port_frame,
            text="Rafraichir",
            command=self.actualiser_ports,
            bg="#222222",
            fg="white",
            activebackground="#333333",
            activeforeground="white",
            highlightthickness=0,
        )
        self.refresh_button.pack(side="left", padx=(0, 8))

        self.connect_button = tk.Button(
            self.port_frame,
            text="Connecter",
            command=self.connecter_port_selectionne,
            bg="#222222",
            fg="white",
            activebackground="#333333",
            activeforeground="white",
            highlightthickness=0,
        )
        self.connect_button.pack(side="left")

        self.status_label = tk.Label(
            root,
            text="Echap ou q pour quitter. Barre espace = declencher une animation.",
            font=("Arial", STATUS_FONT_SIZE),
            fg="gray",
            bg="black",
        )
        self.status_label.grid(row=4, column=0, pady=(0, 8), sticky="ew")

        if serial is None:
            self.status_label.config(text=f"{PYSERIAL_MESSAGE}. Espace = test.")
            self.refresh_button.config(state="disabled")
            self.connect_button.config(state="disabled")
            self.port_menu.config(state="disabled")
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

    def actualiser_ports(self, selection=None):
        ports = lister_ports_disponibles()
        devices = [port["device"] for port in ports]

        if selection is not None and selection not in devices:
            devices.insert(0, selection)

        menu = self.port_menu["menu"]
        menu.delete(0, "end")

        if not devices:
            self.selected_port_var.set("")
            menu.add_command(label="Aucun port", command=lambda: None)
            self.connect_button.config(state="disabled")
            self.status_label.config(text="Aucun port serie detecte.")
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
                elif type_message == "TRIGGER":
                    self.afficher_direction_aleatoire()
                elif type_message == "DIRECTION":
                    self.afficher_direction(contenu)

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
        fullscreen=not args.windowed,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
