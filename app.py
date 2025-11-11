# -*- coding: utf-8 -*-
# Jigsaw Controller - Standalone Tkinter App (ohne Export)
# -------------------------------------------------------------
# Zweck: Lehrpersonen steuern die Jigsaw-/Expertenpuzzle-Methode
# Phasen: (1) Individuelles Lesen, (2) Expertenphase, (3) Stammgruppen
# Features:
#  - Setup-Seite: Namen, Themen, Zeiten, Zufalls-Seed
#  - Automatische Zuteilung moeglichst gleichmaessig
#  - Countdown je Phase (Pause/Weiter/+1 Min)
#  - Manuelle Korrektur: Schueler -> Thema neu zuweisen
#  - Beamer-taugliches UI (grosse Schrift)
#
# Python 3.9+
# Abhaengigkeiten: keine externen Libraries erforderlich
# Start: python app.py
# -------------------------------------------------------------

import json
import random
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox, font as tkfont
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# NEU: fuer DPI-Awareness
import sys
if sys.platform.startswith("win"):
    import ctypes  # wird nur unter Windows importiert

APP_TITLE = "Jigsaw Controller - Expertenpuzzle"
BASE_FONT = ("Segoe UI", 12)
TITLE_FONT = ("Segoe UI", 18, "bold")
TIMER_FONT = ("Segoe UI", 36, "bold")
CARD_TITLE_FONT = ("Segoe UI", 20, "bold")
CARD_ITEM_FONT = ("Segoe UI", 18)
CARD_HINT_FONT = ("Segoe UI", 16)

LIGHT_BACKGROUND = "#F4F6FB"
CARD_BACKGROUND = "#FFFFFF"
CARD_BORDER = "#D0D5DD"
PHASE_BACKGROUNDS = {
    1: "#E3F2FD",  # hellblau
    2: "#E8F5E9",  # hellgruen
    3: "#FFF3E0",  # hellorange
}
PHASE_ACCENTS = {
    1: "#1E88E5",
    2: "#43A047",
    3: "#FB8C00",
}
HEADER_TEXT_COLOR = "#FFFFFF"
PRIMARY_BUTTON_WIDTH = 18

# Icons deaktiviert (ASCII-only)
ICON_SYMBOLS = {
    "load": "",
    "new": "",
    "save": "",
    "delete": "",
    "dice": "",
    "start": "",
    "pause": "",
    "plus": "",
    "next": "",
    "restart": "",
    "shuffle": "",
}

def button_label(icon_key: str, text: str) -> str:
    return text

def icon_only(icon_key: str, fallback: str = "") -> str:
    return ""

DEFAULT_DUR_READ = 8
DEFAULT_DUR_EXPERT = 12
DEFAULT_DUR_STAMM = 15

APP_DIR = Path(__file__).resolve().parent
CLASSES_FILE = APP_DIR / "classes.json"


@dataclass
class AppState:
    students: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    class_name: str = ""
    dur_read: int = DEFAULT_DUR_READ       # Minuten
    dur_expert: int = DEFAULT_DUR_EXPERT   # Minuten
    dur_stamm: int = DEFAULT_DUR_STAMM     # Minuten
    seed: int = field(default_factory=lambda: random.randint(0, 999999))

    # Zuteilungen
    assignment: Dict[str, str] = field(default_factory=dict)  # student -> topic
    experts: Dict[str, List[str]] = field(default_factory=dict)  # topic -> [students]
    stammgruppen: List[List[Tuple[str, str]]] = field(default_factory=list)  # [[(student, topic), ...], ...]
    simple_groups: List[List[str]] = field(default_factory=list)

    phase: int = 1  # 1..3
    seconds_left: int = 0
    running: bool = False


# -------------------- Persistenz --------------------

def load_saved_classes(path: Path) -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return {}, None
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, str(exc)

    if not isinstance(raw, dict):
        return {}, None

    classes: Dict[str, Dict[str, Any]] = {}
    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            continue
        students = [str(s).strip() for s in cfg.get("students", []) if str(s).strip()]
        topics = [str(t).strip() for t in cfg.get("topics", []) if str(t).strip()]
        try:
            dur_read = int(cfg.get("dur_read", DEFAULT_DUR_READ))
            dur_expert = int(cfg.get("dur_expert", DEFAULT_DUR_EXPERT))
            dur_stamm = int(cfg.get("dur_stamm", DEFAULT_DUR_STAMM))
        except (TypeError, ValueError):
            dur_read, dur_expert, dur_stamm = DEFAULT_DUR_READ, DEFAULT_DUR_EXPERT, DEFAULT_DUR_STAMM

        classes[str(name)] = {
            "students": students,
            "topics": topics,
            "dur_read": max(1, dur_read),
            "dur_expert": max(1, dur_expert),
            "dur_stamm": max(1, dur_stamm),
        }

    return classes, None


def save_classes(path: Path, classes: Dict[str, Dict[str, Any]]) -> Optional[str]:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(classes, fh, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError as exc:
        return str(exc)
    return None


# -------------------- Hilfsfunktionen --------------------

def clean_lines(block: str) -> List[str]:
    if not block:
        return []
    raw: List[str] = []
    for line in block.splitlines():
        parts = [p.strip() for p in line.replace(";", ",").split(",")]
        raw.extend([p for p in parts if p])
    # Doppelte entfernen (Reihenfolge beibehalten)
    seen = set()
    out: List[str] = []
    for x in raw:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def assign_topics_evenly(students: List[str], topics: List[str], seed: int = 42) -> Dict[str, str]:
    rng = random.Random(seed)
    shuffled = students.copy()
    rng.shuffle(shuffled)
    mapping: Dict[str, str] = {}
    t = max(1, len(topics))
    for i, s in enumerate(shuffled):
        mapping[s] = topics[i % t]
    return mapping


def invert_to_experts(assignment: Dict[str, str]) -> Dict[str, List[str]]:
    experts: Dict[str, List[str]] = {}
    for student, topic in assignment.items():
        experts.setdefault(topic, []).append(student)
    for k in experts:
        experts[k].sort()
    return experts


def build_stammgruppen(expert_groups: Dict[str, List[str]]) -> List[List[Tuple[str, str]]]:
    topics = list(expert_groups.keys())
    if not topics:
        return []
    groups_count = max((len(members) for members in expert_groups.values()), default=0)
    if groups_count == 0:
        return []
    groups: List[List[Tuple[str, str]]] = [[] for _ in range(groups_count)]
    for topic in topics:
        members = expert_groups.get(topic, [])
        for i, student in enumerate(members):
            groups[i % groups_count].append((student, topic))
    return groups


def build_simple_groups(students: List[str], group_count: int, seed: Optional[int] = None) -> List[List[str]]:
    if group_count <= 0 or not students:
        return []
    count = min(group_count, len(students))
    rng = random.Random(seed) if seed is not None else random.Random()
    shuffled = students.copy()
    rng.shuffle(shuffled)
    groups: List[List[str]] = [[] for _ in range(count)]
    for idx, name in enumerate(shuffled):
        groups[idx % count].append(name)
    return groups


def mmss(sec: int) -> str:
    sec = max(0, int(sec))
    m, s = divmod(sec, 60)
    return f"{m:02d}:{s:02d}"


# -------------------- GUI Frames --------------------

class SetupFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, state: AppState, saved_classes: Dict[str, Dict[str, Any]], on_start, on_classes_changed):
        super().__init__(master, padding=24, style="AppBackground.TFrame")
        self.state = state
        self.saved_classes = saved_classes
        self.on_start = on_start
        self.on_classes_changed = on_classes_changed
        self._defaults = (state.dur_read, state.dur_expert, state.dur_stamm)
        self._simple_group_window: Optional["SimpleGroupsWindow"] = None
        self._build()

    def _build(self):
        # Titelbalken
        self.header_bar = tk.Frame(self, bg="#3949AB")
        self.header_bar.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        tk.Label(
            self.header_bar,
            text=APP_TITLE,
            font=TITLE_FONT,
            fg=HEADER_TEXT_COLOR,
            bg="#3949AB",
        ).pack(side=tk.LEFT, padx=20, pady=12)

        # Klassenverwaltung
        class_box = ttk.Labelframe(self, text="Klasse", style="App.TLabelframe")
        class_box.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        class_box.columnconfigure(1, weight=1)

        ttk.Label(class_box, text="Gespeicherte Klassen:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self.cmb_classes = ttk.Combobox(class_box, values=self._class_names(), state="readonly")
        self.cmb_classes.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.cmb_classes.bind("<<ComboboxSelected>>", self._on_class_chosen)
        ttk.Button(
            class_box,
            text=button_label("load", "Laden"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._load_selected_class,
        ).grid(row=0, column=2, padx=8, pady=8)
        ttk.Button(
            class_box,
            text=button_label("new", "Neu"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._reset_form,
        ).grid(row=0, column=3, padx=(8, 16), pady=8)

        ttk.Label(class_box, text="Name fuer Speichern:").grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")
        self.var_class_name = tk.StringVar(value=self.state.class_name)
        ttk.Entry(class_box, textvariable=self.var_class_name).grid(row=1, column=1, padx=8, pady=(0, 12), sticky="ew")
        self.btn_save_class = ttk.Button(
            class_box,
            text=button_label("save", "Speichern"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._save_class,
        )
        self.btn_save_class.grid(row=1, column=2, padx=8, pady=(0, 12))
        self.btn_delete_class = ttk.Button(
            class_box,
            text=button_label("delete", "Loeschen"),
            style="Danger.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._delete_class,
        )
        self.btn_delete_class.grid(row=1, column=3, padx=(8, 16), pady=(0, 12))

        # Namen
        ttk.Label(self, text="Klasse (Schuelernamen) - je Zeile oder mit Komma", font=BASE_FONT).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.txt_names = tk.Text(self, width=40, height=14, font=BASE_FONT)
        self.txt_names.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(0, 16), pady=(0, 20))

        # Themen
        ttk.Label(self, text="Themen (variabel, typisch 3-6)", font=BASE_FONT).grid(row=2, column=2, columnspan=2, sticky="w", pady=(0, 8))
        self.topics_frame = ttk.Frame(self, style="AppBackground.TFrame")
        self.topics_frame.grid(row=3, column=2, columnspan=2, sticky="nsew", pady=(0, 20))

        self.var_topic_count = tk.IntVar(value=4)
        cnt_row = ttk.Frame(self.topics_frame, style="AppBackground.TFrame")
        cnt_row.pack(anchor="w")
        ttk.Label(cnt_row, text="Anzahl Themen:").pack(side=tk.LEFT)
        ttk.Spinbox(cnt_row, from_=2, to=10, textvariable=self.var_topic_count, width=5, command=self._render_topics_inputs).pack(side=tk.LEFT, padx=(6, 0))

        self.topic_vars: List[tk.StringVar] = []
        self._render_topics_inputs()

        # Zeiten
        times = ttk.Labelframe(self, text="Dauer je Phase (Minuten)", style="App.TLabelframe")
        times.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        self.var_read = tk.IntVar(value=self.state.dur_read)
        self.var_expert = tk.IntVar(value=self.state.dur_expert)
        self.var_stamm = tk.IntVar(value=self.state.dur_stamm)
        ttk.Label(times, text="Individuelles Lesen:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        ttk.Spinbox(times, from_=1, to=90, textvariable=self.var_read, width=6).grid(row=0, column=1, padx=12, pady=8)
        ttk.Label(times, text="Expertenphase:").grid(row=0, column=2, padx=12, pady=8, sticky="w")
        ttk.Spinbox(times, from_=1, to=90, textvariable=self.var_expert, width=6).grid(row=0, column=3, padx=12, pady=8)
        ttk.Label(times, text="Stammgruppenphase:").grid(row=0, column=4, padx=12, pady=8, sticky="w")
        ttk.Spinbox(times, from_=1, to=90, textvariable=self.var_stamm, width=6).grid(row=0, column=5, padx=12, pady=8)

        # Seed
        seed_row = ttk.Frame(self, style="AppBackground.TFrame")
        seed_row.grid(row=5, column=0, columnspan=4, sticky="w", pady=(0, 20))
        ttk.Label(seed_row, text="Zufalls-Seed:").pack(side=tk.LEFT)
        self.var_seed = tk.IntVar(value=self.state.seed)
        ttk.Spinbox(seed_row, from_=0, to=999999, textvariable=self.var_seed, width=8).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            seed_row,
            text=icon_only("dice", ""),
            style="SmallIcon.TButton",
            width=4,
            command=self._randomize_seed,
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Einfachgruppen
        simple_box = ttk.Labelframe(self, text="Einfachgruppen", style="App.TLabelframe")
        simple_box.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        simple_box.columnconfigure(1, weight=1)
        ttk.Label(simple_box, text="Lernende zufaellig in Gruppen einteilen:").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self.var_simple_group_count = tk.IntVar(value=4)
        ttk.Spinbox(simple_box, from_=2, to=12, textvariable=self.var_simple_group_count, width=6).grid(row=0, column=1, padx=12, pady=8, sticky="w")
        ttk.Button(
            simple_box,
            text=button_label("start", "Gruppen bilden"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._open_simple_groups,
        ).grid(row=0, column=2, padx=(8, 16), pady=8, sticky="e")

        # Start-Button
        start_btn = ttk.Button(
            self,
            text=button_label("start", "Start"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._start,
        )
        start_btn.grid(row=7, column=0, sticky="w", pady=(0, 0))

        # Grid-Konfiguration
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)
        self._update_delete_state()

    def _class_names(self) -> List[str]:
        return sorted(self.saved_classes.keys())

    def _refresh_class_options(self, selected: str = "") -> None:
        names = self._class_names()
        self.cmb_classes.configure(values=names)
        if selected and selected in names:
            self.cmb_classes.set(selected)
        elif selected:
            self.cmb_classes.set("")
        elif not names:
            self.cmb_classes.set("")
        self._update_delete_state()

    def _update_delete_state(self) -> None:
        if hasattr(self, "btn_delete_class"):
            state = "normal" if self._class_names() else "disabled"
            self.btn_delete_class.config(state=state)

    def _render_topics_inputs(self, topics: Optional[List[str]] = None):
        # Loescht alte
        for w in getattr(self, "_topic_entries", []):
            w.destroy()
        self._topic_entries = []
        previous = topics if topics is not None else [var.get().strip() for var in getattr(self, "topic_vars", [])]
        self.topic_vars = []
        count = max(2, int(self.var_topic_count.get()))
        for i in range(count):
            label = previous[i] if i < len(previous) and previous[i] else f"Thema {i + 1}"
            var = tk.StringVar(value=label)
            self.topic_vars.append(var)
            e = ttk.Entry(self.topics_frame, textvariable=var, width=30)
            e.pack(anchor="w", pady=4, fill="x")
            self._topic_entries.append(e)

    def _randomize_seed(self) -> None:
        self.var_seed.set(random.randint(0, 999999))

    def _reset_form(self) -> None:
        self.cmb_classes.set("")
        self.var_class_name.set("")
        self.txt_names.delete("1.0", tk.END)
        self.var_topic_count.set(4)
        self._render_topics_inputs()
        self.var_read.set(self._defaults[0])
        self.var_expert.set(self._defaults[1])
        self.var_stamm.set(self._defaults[2])
        self._randomize_seed()
        self.state.class_name = ""
        self._update_delete_state()

    def _on_class_chosen(self, _event=None):
        self._load_selected_class()

    def _load_selected_class(self, name: Optional[str] = None) -> None:
        if name is None:
            name = self.cmb_classes.get().strip()
        if not name:
            return
        cfg = self.saved_classes.get(name)
        if not cfg:
            messagebox.showwarning("Hinweis", f"Klasse '{name}' konnte nicht gefunden werden.")
            return
        self.state.class_name = name
        self.var_class_name.set(name)
        students = cfg.get("students", [])
        self.txt_names.delete("1.0", tk.END)
        self.txt_names.insert("1.0", "\n".join(students))
        topics = cfg.get("topics", [])
        count = max(2, len(topics) or 4)
        self.var_topic_count.set(count)
        self._render_topics_inputs(topics if topics else None)
        try:
            self.var_read.set(int(cfg.get("dur_read", self._defaults[0])))
        except (TypeError, ValueError):
            self.var_read.set(self._defaults[0])
        try:
            self.var_expert.set(int(cfg.get("dur_expert", self._defaults[1])))
        except (TypeError, ValueError):
            self.var_expert.set(self._defaults[1])
        try:
            self.var_stamm.set(int(cfg.get("dur_stamm", self._defaults[2])))
        except (TypeError, ValueError):
            self.var_stamm.set(self._defaults[2])
        self._randomize_seed()
        self._refresh_class_options(selected=name)

    def _save_class(self) -> None:
        name = self.var_class_name.get().strip()
        if not name:
            messagebox.showwarning("Hinweis", "Bitte einen Namen fuer die Klasse angeben.")
            return
        students = clean_lines(self.txt_names.get("1.0", tk.END))
        topics = [v.get().strip() for v in self.topic_vars if v.get().strip()]
        if not students:
            messagebox.showwarning("Hinweis", "Zum Speichern bitte mindestens einen Schuelernamen eingeben.")
            return
        if len(topics) < 1:
            messagebox.showwarning("Hinweis", "Zum Speichern bitte mindestens ein Thema erfassen.")
            return

        config = {
            "students": students,
            "topics": topics,
            "dur_read": int(self.var_read.get()),
            "dur_expert": int(self.var_expert.get()),
            "dur_stamm": int(self.var_stamm.get()),
        }
        previous = self.saved_classes.get(name)
        self.saved_classes[name] = config
        self.state.class_name = name
        self._refresh_class_options(selected=name)
        if callable(self.on_classes_changed):
            error = self.on_classes_changed()
            if error:
                if previous is None:
                    self.saved_classes.pop(name, None)
                else:
                    self.saved_classes[name] = previous
                self._refresh_class_options(selected=previous and name or "")
                messagebox.showerror("Fehler", f"Klasse konnte nicht gespeichert werden:\n{error}")
                return
        messagebox.showinfo("Gespeichert", f"Klasse '{name}' wurde gesichert.")

    def _delete_class(self) -> None:
        name = self.cmb_classes.get().strip() or self.var_class_name.get().strip()
        if not name or name not in self.saved_classes:
            messagebox.showwarning("Hinweis", "Bitte zuerst eine gespeicherte Klasse auswaehlen.")
            return
        if not messagebox.askyesno("Loeschen", f"Klasse '{name}' wirklich loeschen?"):
            return
        config = self.saved_classes.pop(name)
        if callable(self.on_classes_changed):
            error = self.on_classes_changed()
            if error:
                self.saved_classes[name] = config
                self._refresh_class_options(selected=name)
                messagebox.showerror("Fehler", f"Klasse konnte nicht geloescht werden:\n{error}")
                return
        self._refresh_class_options()
        self._reset_form()
        messagebox.showinfo("Geloescht", f"Klasse '{name}' wurde entfernt.")

    def _open_simple_groups(self) -> None:
        try:
            count = max(2, int(self.var_simple_group_count.get()))
        except (TypeError, ValueError):
            messagebox.showwarning("Hinweis", "Bitte eine gueltige Gruppenzahl angeben (mindestens 2).")
            return
        students = clean_lines(self.txt_names.get("1.0", tk.END))
        if len(students) < count:
            messagebox.showwarning(
                "Hinweis",
                "Es werden mehr Lernende benoetigt als Gruppen vorhanden sind. Bitte Liste pruefen.",
            )
            return
        seed = random.randint(0, 999999)
        groups = build_simple_groups(students, count, seed=seed)

        self.state.simple_groups = groups
        if self._simple_group_window and self._simple_group_window.winfo_exists():
            self._simple_group_window.destroy()
        self._simple_group_window = SimpleGroupsWindow(
            self.winfo_toplevel(),
            groups,
            seed=seed,
            class_name=self.state.class_name or self.var_class_name.get().strip() or "-",
        )

    def _start(self):
        students = clean_lines(self.txt_names.get("1.0", tk.END))
        topics = [v.get().strip() for v in self.topic_vars if v.get().strip()]
        if len(students) < 2:
            messagebox.showerror("Fehler", "Bitte mindestens 2 Schuelernamen eingeben.")
            return
        if len(topics) < 2:
            messagebox.showerror("Fehler", "Bitte mindestens 2 Themen eingeben.")
            return
        self.state.class_name = self.var_class_name.get().strip()
        self.state.students = students
        self.state.topics = topics
        self.state.dur_read = int(self.var_read.get())
        self.state.dur_expert = int(self.var_expert.get())
        self.state.dur_stamm = int(self.var_stamm.get())
        self.state.seed = int(self.var_seed.get())

        if self._simple_group_window and self._simple_group_window.winfo_exists():
            self._simple_group_window.destroy()
            self._simple_group_window = None

        self.state.assignment = assign_topics_evenly(self.state.students, self.state.topics, seed=self.state.seed)
        self.state.experts = invert_to_experts(self.state.assignment)
        self.state.stammgruppen = build_stammgruppen(self.state.experts)
        self.state.simple_groups = []

        self.state.phase = 1
        self.state.seconds_left = self.state.dur_read * 60
        self.state.running = False  # startet pausiert
        self.on_start()


class SimpleGroupsWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, groups: List[List[str]], seed: int, class_name: str = "-"):
        super().__init__(master)
        self.title("Einfachgruppen")
        self.groups = groups
        self.seed = seed
        self.class_name = class_name or "-"
        self.configure(bg=LIGHT_BACKGROUND)
        self.geometry("960x640")
        self.minsize(780, 520)
        try:
            self.transient(master)
        except Exception:
            pass
        self.focus_set()

        self.font_header = tkfont.Font(family="Segoe UI", size=32, weight="bold")
        self.font_meta = tkfont.Font(family="Segoe UI", size=18)
        self.font_group_title = tkfont.Font(family="Segoe UI", size=26, weight="bold")
        self.font_member = tkfont.Font(family="Segoe UI", size=22)
        self.font_hint = tkfont.Font(family="Segoe UI", size=20)

        self.container = ttk.Frame(self, padding=24, style="AppBackground.TFrame")
        self.container.pack(fill="both", expand=True)

        self.header_bar = tk.Frame(self.container, bg="#3949AB")
        self.header_bar.pack(fill="x", pady=(0, 20))
        tk.Label(
            self.header_bar,
            text="Einfachgruppen",
            font=self.font_header,
            fg=HEADER_TEXT_COLOR,
            bg="#3949AB",
        ).pack(side=tk.LEFT, padx=20, pady=12)
        tk.Label(
            self.header_bar,
            text=f"Klasse: {self.class_name}    |    Gruppen: {len(groups)}    |    Seed: {self.seed:06d}",
            font=self.font_meta,
            fg=HEADER_TEXT_COLOR,
            bg="#3949AB",
        ).pack(side=tk.LEFT, padx=(12, 0))

        self.groups_frame = ttk.Frame(self.container, style="AppBackground.TFrame")
        self.groups_frame.pack(fill="both", expand=True)

        self._render_groups()
        self.bind("<Configure>", self._on_resize)
        self.after(0, self._update_font_sizes)

    def _render_groups(self) -> None:
        for child in self.groups_frame.winfo_children():
            child.destroy()
        if not self.groups:
            ttk.Label(
                self.groups_frame,
                text="Keine Lernenden vorhanden.",
                font=self.font_hint,
                foreground="#6B7280",
            ).pack(expand=True)
            return

        columns = min(4, max(1, len(self.groups)))
        for idx in range(columns):
            self.groups_frame.columnconfigure(idx, weight=1)

        for i, group in enumerate(self.groups, start=1):
            col = (i - 1) % columns
            card = ttk.Frame(self.groups_frame, style="CardBody.TFrame", padding=16)
            card.grid(row=(i - 1) // columns, column=col, padx=10, pady=10, sticky="nsew")
            ttk.Label(card, text=f"Gruppe {i}", font=self.font_group_title).pack(anchor="w", pady=(0, 8))
            if group:
                for name in group:
                    ttk.Label(card, text=name, font=self.font_member).pack(anchor="w", padx=6, pady=2)
            else:
                ttk.Label(
                    card,
                    text="(leer)",
                    font=self.font_hint,
                    foreground="#6B7280",
                ).pack(anchor="w", padx=6, pady=2)

    def _on_resize(self, _event=None) -> None:
        self._update_font_sizes()

    def _update_font_sizes(self) -> None:
        width = max(self.winfo_width(), 780)
        height = max(self.winfo_height(), 520)
        scale = min(width / 960, height / 640)
        scale = max(0.9, min(scale, 2.2))
        self.font_header.configure(size=max(26, int(32 * scale)))
        self.font_meta.configure(size=max(16, int(18 * scale)))
        self.font_group_title.configure(size=max(22, int(26 * scale)))
        self.font_member.configure(size=max(18, int(22 * scale)))
        self.font_hint.configure(size=max(16, int(20 * scale)))


class PhaseFrame(ttk.Frame):
    def __init__(self, master: tk.Misc, state: AppState, on_restart):
        super().__init__(master)
        self.state = state
        self.on_restart = on_restart
        self._timer_job = None
        self.style = ttk.Style(self)
        self.fonts = {
            "header_title": tkfont.Font(family="Segoe UI", size=32, weight="bold"),
            "header_meta": tkfont.Font(family="Segoe UI", size=18),
            "timer": tkfont.Font(family="Segoe UI", size=84, weight="bold"),
            "card_title": tkfont.Font(family="Segoe UI", size=26, weight="bold"),
            "card_item": tkfont.Font(family="Segoe UI", size=22),
            "card_hint": tkfont.Font(family="Segoe UI", size=20),
            "button": tkfont.Font(family="Segoe UI", size=18),
            "combo": tkfont.Font(family="Segoe UI", size=18),
        }
        self.style.configure("Card.TLabelframe.Label", font=self.fonts["card_title"])
        self.style.configure("CardTitle.TLabel", font=self.fonts["card_title"])
        self.style.configure("CardItem.TLabel", font=self.fonts["card_item"])
        self.style.configure("CardHint.TLabel", font=self.fonts["card_hint"])
        self.style.configure("Modern.TButton", font=self.fonts["button"])
        self.style.configure("Danger.TButton", font=self.fonts["button"])
        self.phase_frames: List[ttk.Frame] = []
        self.content = ttk.Frame(self, padding=24)
        self.content.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.content.columnconfigure(1, weight=1)
        self.content.columnconfigure(2, weight=1)
        self.content.rowconfigure(2, weight=1)
        self.content.rowconfigure(3, weight=1)
        self._build()
        self._render()
        self.bind("<Configure>", self._on_resize)
        self.after(0, self._update_font_sizes)

    def _frame_style(self, phase: int) -> str:
        return f"Phase{phase}.TFrame"

    def _apply_phase_theme(self):
        phase = self.state.phase
        bg = PHASE_BACKGROUNDS.get(phase, PHASE_BACKGROUNDS[1])
        accent = PHASE_ACCENTS.get(phase, PHASE_ACCENTS[1])
        style_name = self._frame_style(phase)
        self.style.configure(style_name, background=bg)
        self.configure(style=style_name)
        self.content.configure(style=style_name)
        for frame in self.phase_frames:
            frame.configure(style=style_name)
        self.header_bar.configure(bg=accent)
        self.lbl_title.configure(bg=accent, fg=HEADER_TEXT_COLOR)
        self.lbl_phase.configure(bg=accent, fg=HEADER_TEXT_COLOR)
        self.lbl_timer.configure(bg=bg)

    def _on_resize(self, _event=None) -> None:
        self._update_font_sizes()

    def _update_font_sizes(self) -> None:
        width = max(self.winfo_width(), 980)
        height = max(self.winfo_height(), 640)
        scale = min(width / 1280, height / 720)
        scale = max(0.9, min(scale, 2.5))
        self.fonts["header_title"].configure(size=max(28, int(36 * scale)))
        self.fonts["header_meta"].configure(size=max(18, int(20 * scale)))
        self.fonts["timer"].configure(size=max(64, int(98 * scale)))
        self.fonts["card_title"].configure(size=max(22, int(28 * scale)))
        self.fonts["card_item"].configure(size=max(20, int(24 * scale)))
        self.fonts["card_hint"].configure(size=max(18, int(22 * scale)))
        self.fonts["button"].configure(size=max(16, int(20 * scale)))
        self.fonts["combo"].configure(size=max(16, int(20 * scale)))

    def _build(self):
        frame_style = self._frame_style(self.state.phase)

        # Header
        self.header_container = ttk.Frame(self.content, style=frame_style)
        self.header_container.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.phase_frames.append(self.header_container)
        self.header_bar = tk.Frame(self.header_container, bg=PHASE_ACCENTS.get(self.state.phase, "#1E88E5"))
        self.header_bar.pack(fill="x", pady=(0, 20))
        self.lbl_title = tk.Label(
            self.header_bar,
            text="",
            font=self.fonts["header_title"],
            fg=HEADER_TEXT_COLOR,
            bg=self.header_bar["bg"],
        )
        self.lbl_title.pack(side=tk.LEFT, padx=20, pady=12)
        self.lbl_phase = tk.Label(
            self.header_bar,
            text="",
            font=self.fonts["header_meta"],
            fg=HEADER_TEXT_COLOR,
            bg=self.header_bar["bg"],
        )
        self.lbl_phase.pack(side=tk.LEFT, padx=(12, 0))

        # Timer + Controls
        self.ctrl = ttk.Frame(self.content, style=frame_style)
        self.ctrl.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 20))
        self.phase_frames.append(self.ctrl)
        self.lbl_timer = tk.Label(
            self.ctrl,
            text=mmss(self.state.seconds_left),
            font=self.fonts["timer"],
            bg=PHASE_BACKGROUNDS.get(self.state.phase, PHASE_BACKGROUNDS[1]),
            fg="#1B1C1E",
        )
        self.lbl_timer.pack(side=tk.LEFT, padx=(0, 24))

        self.btn_toggle = ttk.Button(
            self.ctrl,
            text=button_label("start", "Start/Weiter"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._toggle,
        )
        self.btn_toggle.pack(side=tk.LEFT, padx=8)
        ttk.Button(
            self.ctrl,
            text=button_label("plus", "+1 Min"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._plus_minute,
        ).pack(side=tk.LEFT, padx=8)
        self.btn_next = ttk.Button(
            self.ctrl,
            text=button_label("next", "Weiter"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._next,
        )
        self.btn_next.pack(side=tk.LEFT, padx=8)
        ttk.Button(
            self.ctrl,
            text=button_label("restart", "Neu starten"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._restart,
        ).pack(side=tk.LEFT, padx=(24, 0))

        # Anpassung: Schueler -> Thema
        adj = ttk.Labelframe(self.content, text="Zuteilung anpassen (Phase 1)", style="Card.TLabelframe")
        adj.grid(row=2, column=2, sticky="nsew", padx=(20, 0))
        adj.columnconfigure(0, weight=1)
        inner_adj = ttk.Frame(adj, style="CardBody.TFrame", padding=12)
        inner_adj.grid(row=0, column=0, sticky="nsew")
        inner_adj.columnconfigure(0, weight=1)
        self.cmb_student = ttk.Combobox(inner_adj, values=self.state.students, state="readonly", font=self.fonts["combo"])
        self.cmb_student.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        self.cmb_topic = ttk.Combobox(inner_adj, values=self.state.topics, state="readonly", font=self.fonts["combo"])
        self.cmb_topic.grid(row=1, column=0, padx=6, pady=6, sticky="ew")
        self.btn_apply = ttk.Button(inner_adj, text="Anwenden", style="Modern.TButton", width=PRIMARY_BUTTON_WIDTH, command=self._apply_change)
        self.btn_apply.grid(row=2, column=0, padx=6, pady=6, sticky="ew")
        self.btn_shuffle = ttk.Button(
            inner_adj,
            text=button_label("shuffle", "Neu zuteilen"),
            style="Modern.TButton",
            width=PRIMARY_BUTTON_WIDTH,
            command=self._reshuffle,
        )
        self.btn_shuffle.grid(row=3, column=0, padx=6, pady=(0, 6), sticky="ew")

        # Inhaltsspalten
        self.col_left = ttk.Frame(self.content, style=frame_style)
        self.col_left.grid(row=2, column=0, rowspan=2, sticky="nsew", padx=(0, 20))
        self.col_mid = ttk.Frame(self.content, style=frame_style)
        self.col_mid.grid(row=2, column=1, rowspan=2, sticky="nsew", padx=(0, 20))
        self.phase_frames.extend([self.content, self.col_left, self.col_mid])

    # ---------- Timer ----------
    def _tick(self):
        if self.state.running:
            if self.state.seconds_left > 0:
                self.state.seconds_left -= 1
                self.lbl_timer.config(text=mmss(self.state.seconds_left))
                self._timer_job = self.after(1000, self._tick)
            else:
                self.state.running = False
                self.lbl_timer.config(text=mmss(0))
                self.bell()
        else:
            pass

    def _toggle(self):
        self.state.running = not self.state.running
        if self.state.running:
            self.btn_toggle.config(text=button_label("pause", "Pause"))
            self._tick()
        else:
            self.btn_toggle.config(text=button_label("start", "Start/Weiter"))

    def _plus_minute(self):
        self.state.seconds_left += 60
        self.lbl_timer.config(text=mmss(self.state.seconds_left))

    def _next(self):
        # laufenden Timer-Job abbrechen, falls aktiv
        if self._timer_job is not None:
            try:
                self.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None

        if self.state.phase < 3:
            self.state.phase += 1
            self.state.running = False
            self.btn_toggle.config(text=button_label("start", "Start/Weiter"))
            if self.state.phase == 2:
                self.state.seconds_left = self.state.dur_expert * 60
            elif self.state.phase == 3:
                self.state.seconds_left = self.state.dur_stamm * 60
            # Beim Wechsel ggf. Stammgruppen neu bauen (falls Zuteilung geaendert wurde)
            self.state.experts = invert_to_experts(self.state.assignment)
            self.state.stammgruppen = build_stammgruppen(self.state.experts)
            self._render()
        else:
            self.state.running = False
            self.btn_toggle.config(text=button_label("start", "Start/Weiter"))
            messagebox.showinfo("Abschluss", "Jigsaw-Durchlauf beendet.")

    def _restart(self):
        if messagebox.askyesno("Neu starten", "Zurueck zum Setup und alles zuruecksetzen?"):
            # Timer-Job stoppen
            if self._timer_job is not None:
                try:
                    self.after_cancel(self._timer_job)
                except Exception:
                    pass
                self._timer_job = None
            self.on_restart()

    def _apply_change(self):
        s = self.cmb_student.get()
        t = self.cmb_topic.get()
        if not s or not t:
            messagebox.showwarning("Hinweis", "Bitte Schueler und Thema waehlen.")
            return
        self.state.assignment[s] = t
        self.state.experts = invert_to_experts(self.state.assignment)
        self.state.stammgruppen = build_stammgruppen(self.state.experts)
        self.cmb_student.set("")
        self.cmb_topic.set("")
        self._render()

    def _reshuffle(self):
        if self.state.phase != 1:
            messagebox.showwarning("Hinweis", "Neu zuteilen ist nur in Phase 1 moeglich.")
            return
        if not self.state.students or not self.state.topics:
            messagebox.showwarning("Hinweis", "Bitte zuerst Schueler und Themen erfassen.")
            return
        self.state.seed = random.randint(0, 999999)
        self.state.assignment = assign_topics_evenly(self.state.students, self.state.topics, seed=self.state.seed)
        self.state.experts = invert_to_experts(self.state.assignment)
        self.state.stammgruppen = build_stammgruppen(self.state.experts)
        self.cmb_student.set("")
        self.cmb_topic.set("")
        self._render()

    # ---------- Render ----------
    def _clear_cols(self):
        for col in (self.col_left, self.col_mid):
            for w in col.winfo_children():
                w.destroy()

    def _render_lists(self, parent, title: str, groups: Dict[str, List[str]]):
        wrap = ttk.Labelframe(parent, text=title, style="Card.TLabelframe")
        wrap.pack(fill="both", expand=True, padx=4, pady=4)

        inner = ttk.Frame(wrap, style="CardBody.TFrame", padding=24)
        inner.pack(fill="both", expand=True)

        cols = [ttk.Frame(inner, style="CardBody.TFrame") for _ in range(2)]
        cols[0].pack(side=tk.LEFT, fill="both", expand=True, padx=(0, 14))
        cols[1].pack(side=tk.LEFT, fill="both", expand=True, padx=(14, 0))

        items = list(groups.items())
        for i, (topic, members) in enumerate(items):
            box = ttk.Frame(cols[i % 2], style="CardBody.TFrame", padding=12)
            box.pack(fill="x", expand=True, pady=12)

            ttk.Label(box, text=f"{topic}", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
            if members:
                for s in members:
                    ttk.Label(box, text=f"• {s}", style="CardItem.TLabel").pack(anchor="w", padx=6, pady=4)
            else:
                ttk.Label(box, text="(keine Zuteilung)", style="CardHint.TLabel").pack(anchor="w", padx=6)

    def _render_stamm(self, parent, groups: List[List[Tuple[str, str]]]):
        wrap = ttk.Labelframe(parent, text="Stammgruppen", style="Card.TLabelframe")
        wrap.pack(fill="both", expand=True, padx=4, pady=4)

        inner = ttk.Frame(wrap, style="CardBody.TFrame", padding=24)
        inner.pack(fill="both", expand=True)

        cols = [ttk.Frame(inner, style="CardBody.TFrame") for _ in range(3)]
        for i, c in enumerate(cols):
            c.pack(side=tk.LEFT, fill="both", expand=True, padx=14)

        for i, grp in enumerate(groups, start=1):
            box = ttk.Frame(cols[(i - 1) % 3], style="CardBody.TFrame", padding=12)
            box.pack(fill="x", expand=True, pady=12)

            ttk.Label(box, text=f"Stammgruppe {i}", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 10))
            if grp:
                for s, t in sorted(grp, key=lambda x: x[0]):
                    ttk.Label(box, text=f"• {s}  [ {t} ]", style="CardItem.TLabel").pack(anchor="w", padx=6, pady=4)
            else:
                ttk.Label(box, text="(leer)", style="CardHint.TLabel").pack(anchor="w", padx=6)

    def _render(self):
        # Titel/Phase
        names = {1: "Individuelles Lesen", 2: "Expertenphase", 3: "Stammgruppenphase"}
        self.lbl_title.config(text=names[self.state.phase])
        class_label = self.state.class_name or "-"
        self.lbl_phase.config(
            text=(
                f"Phase {self.state.phase} von 3    |    Klasse: {class_label}"
                f"    |    Themen: {len(self.state.topics)}    |    Seed: {self.state.seed}"
            )
        )
        self._apply_phase_theme()
        self.lbl_timer.config(text=mmss(self.state.seconds_left))
        self.btn_toggle.config(
            text=button_label("pause", "Pause") if self.state.running else button_label("start", "Start/Weiter")
        )
        self.btn_next.config(
            text=button_label("next", "Weiter") if self.state.phase < 3 else "Abschluss"
        )

        self.cmb_student.configure(values=self.state.students)
        self.cmb_topic.configure(values=self.state.topics)
        if self.state.phase == 1 and self.state.students and self.state.topics:
            self.cmb_student.config(state="readonly")
            self.cmb_topic.config(state="readonly")
            self.btn_apply.config(state="normal")
            self.btn_shuffle.config(state="normal")
        elif self.state.phase == 1:
            self.cmb_student.set("")
            self.cmb_topic.set("")
            self.cmb_student.config(state="disabled")
            self.cmb_topic.config(state="disabled")
            self.btn_apply.config(state="disabled")
            self.btn_shuffle.config(state="disabled")
        else:
            self.cmb_student.set("")
            self.cmb_topic.set("")
            self.cmb_student.config(state="disabled")
            self.cmb_topic.config(state="disabled")
            self.btn_apply.config(state="disabled")
            self.btn_shuffle.config(state="disabled")

        self._clear_cols()

        if self.state.phase == 1:
            # Anzeige: Thema -> Schueler (aus assignment)
            groups: Dict[str, List[str]] = {t: [] for t in self.state.topics}
            for s, t in self.state.assignment.items():
                groups.setdefault(t, []).append(s)
            for t in groups:
                groups[t].sort()
            self._render_lists(self.col_left, "Themen & zugeordnete Schueler", groups)
        elif self.state.phase == 2:
            # Experten-Gruppen
            self._render_lists(self.col_left, "Expertengruppen je Thema", self.state.experts)
        else:
            # Stammgruppen
            self._render_stamm(self.col_left, self.state.stammgruppen)

        hints = {
            1: "Hinweis: Zuteilungen koennen rechts angepasst werden.",
            2: "Bereitet pro Thema ein kurzes Merkblatt/Poster vor.",
            3: "Jede Gruppe hat idealerweise 1 Person pro Thema.",
        }
        wrap = max(360, int(self.winfo_width() * 0.28))
        tk.Label(
            self.col_mid,
            text=hints.get(self.state.phase, ""),
            fg="#2D3748",
            bg=PHASE_BACKGROUNDS.get(self.state.phase, PHASE_BACKGROUNDS[1]),
            wraplength=wrap,
            justify=tk.LEFT,
            font=self.fonts["card_hint"],
        ).pack(anchor="nw", pady=12, padx=6)


# -------------------- Hauptanwendung --------------------

class JigsawApp(tk.Tk):
    def __init__(self):
        super().__init__()

        # NEU: DPI-Awareness frueh setzen
        self._setup_dpi_awareness()

        self.title(APP_TITLE)
        classes, error = load_saved_classes(CLASSES_FILE)
        self.saved_classes: Dict[str, Dict[str, Any]] = classes
        if error:
            messagebox.showwarning("Hinweis", f"Gespeicherte Klassen konnten nicht geladen werden:\n{error}")
        self.state_data = AppState()
        # Groessere Standard-Schrift
        self.option_add("*Font", BASE_FONT)
        # Styles
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass
        self._configure_styles()
        # Fenstergroesse
        self.geometry("1100x750")
        self.minsize(980, 640)

        # NEU: Beim Start maximieren (hilft bei kleinen Bildschirmen/Skalierung)
        self.after(50, self._maximize)

        # Frames
        self.setup_frame: Optional[SetupFrame] = None
        self.phase_frame: Optional[PhaseFrame] = None
        self._create_setup_frame()
        # Menue
        self._build_menu()

    # NEU: DPI-Awareness + tk scaling
    def _setup_dpi_awareness(self):
        if sys.platform.startswith("win"):
            # Prozess DPI-aware machen (verhindert doppelte Skalierung)
            try:
                # Windows 8.1+ (System DPI aware)
                ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 1=System, 2=Per-Monitor (optional)
            except Exception:
                try:
                    # Fallback (Windows 7/8)
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
            # Tk-Scaling passend zu DPI
            dpi = 96
            try:
                # Windows 10+: fensterbezogene DPI
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                else:
                    dpi = ctypes.windll.shcore.GetDpiForSystem()
            except Exception:
                pass
            try:
                self.tk.call("tk", "scaling", float(dpi) / 96.0)
            except Exception:
                pass

    # NEU: Zoom/Scaling setter
    def _set_scaling(self, factor: float):
        try:
            self.tk.call("tk", "scaling", float(factor))
        except Exception:
            pass

    # NEU: Maximieren
    def _maximize(self):
        try:
            self.state("zoomed")  # Windows
        except Exception:
            try:
                self.attributes("-zoomed", True)  # Linux
            except Exception:
                self.geometry("1280x800")  # Fallback

    def _configure_styles(self) -> None:
        self.style.configure("AppBackground.TFrame", background=LIGHT_BACKGROUND)
        self.style.configure("App.TLabelframe", background=LIGHT_BACKGROUND, borderwidth=0, padding=16)
        self.style.configure("App.TLabelframe.Label", background=LIGHT_BACKGROUND, font=("Segoe UI", 13, "bold"))

        self.style.configure("Card.TLabelframe", background=CARD_BACKGROUND, borderwidth=1, relief="solid", padding=18, bordercolor=CARD_BORDER)
        self.style.configure("Card.TLabelframe.Label", background=CARD_BACKGROUND, font=CARD_TITLE_FONT)
        self.style.configure("CardBody.TFrame", background=CARD_BACKGROUND)
        self.style.configure("CardTitle.TLabel", background=CARD_BACKGROUND, foreground="#1B1C1E", font=CARD_TITLE_FONT)
        self.style.configure("CardItem.TLabel", background=CARD_BACKGROUND, foreground="#1B1C1E", font=CARD_ITEM_FONT)
        self.style.configure("CardHint.TLabel", background=CARD_BACKGROUND, foreground="#6B7280", font=CARD_HINT_FONT)

        button_padding = (16, 12)
        self.style.configure("Modern.TButton", padding=button_padding, font=("Segoe UI", 14))
        self.style.configure("Danger.TButton", padding=button_padding, font=("Segoe UI", 14), foreground="#B3261E")
        self.style.map("Danger.TButton", foreground=[("disabled", "#9CA3AF"), ("active", "#8B1B15")])
        self.style.configure("SmallIcon.TButton", padding=(10, 6))

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Beenden", command=self.destroy)
        menubar.add_cascade(label="Datei", menu=filemenu)

        # NEU: Ablauf -> Start (falls Button mal nicht sichtbar ist)
        runmenu = tk.Menu(menubar, tearoff=0)
        runmenu.add_command(
            label="Start (Setup)",
            command=lambda: (self.setup_frame and hasattr(self.setup_frame, "_start") and self.setup_frame._start())
        )
        menubar.add_cascade(label="Ablauf", menu=runmenu)

        # NEU: Ansicht -> Maximieren + Zoom-Presets
        viewmenu = tk.Menu(menubar, tearoff=0)
        viewmenu.add_command(label="Maximieren", command=self._maximize)
        viewmenu.add_separator()
        viewmenu.add_command(label="Zoom 90 %", command=lambda: self._set_scaling(0.90))
        viewmenu.add_command(label="Zoom 100 %", command=lambda: self._set_scaling(1.00))
        viewmenu.add_command(label="Zoom 125 %", command=lambda: self._set_scaling(1.25))
        viewmenu.add_command(label="Zoom 150 %", command=lambda: self._set_scaling(1.50))
        menubar.add_cascade(label="Ansicht", menu=viewmenu)

        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="Ueber", command=lambda: messagebox.showinfo("Ueber", "Jigsaw Controller - Tkinter\nErstellt mit ChatGPT"))
        menubar.add_cascade(label="Hilfe", menu=helpmenu)

    def _to_phase(self):
        if self.phase_frame:
            self.phase_frame.destroy()
        self.setup_frame.pack_forget()
        self.phase_frame = PhaseFrame(self, self.state_data, on_restart=self._restart)
        self.phase_frame.pack(fill="both", expand=True)

    def _create_setup_frame(self):
        if self.setup_frame:
            self.setup_frame.destroy()
        self.setup_frame = SetupFrame(
            self,
            self.state_data,
            self.saved_classes,
            on_start=self._to_phase,
            on_classes_changed=self._persist_classes,
        )
        self.setup_frame.pack(fill="both", expand=True)

    def _persist_classes(self) -> Optional[str]:
        return save_classes(CLASSES_FILE, self.saved_classes)

    def _restart(self):
        # kompletten State zuruecksetzen und zum Setup zurueck
        self.state_data = AppState()
        if self.phase_frame:
            self.phase_frame.destroy()
            self.phase_frame = None
        self._create_setup_frame()


def main():
    app = JigsawApp()
    app.mainloop()


if __name__ == "__main__":
    main()

