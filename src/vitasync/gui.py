"""Fenêtre de VitaSync (Tkinter) : état des jeux et synchronisation en un clic.

La fenêtre ne fait qu'afficher et déclencher : tout le travail passe par
:mod:`vitasync.service`, comme la ligne de commande. Les échanges avec la
Vita tournent dans un fil d'exécution à part pour ne pas figer la fenêtre ;
ils renvoient leurs résultats par une file que la fenêtre relit toutes les
100 ms.
"""

import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk
from typing import Any

from vitasync import __version__, service
from vitasync.ftp import VitaFtpClient
from vitasync.manifest import GameManifest, builtin_manifests
from vitasync.service import GameStatus

POLL_MS = 100


def format_progress(value: int | None, in_levels: bool) -> str:
    """Affiche un avancement : ``47:40:34``, ``4 niveaux`` ou ``-`` si vide.

    Args:
        value: Temps de jeu en secondes ou nombre de niveaux.
        in_levels: ``True`` pour un nombre de niveaux.

    Returns:
        Le texte à afficher.
    """
    if value is None:
        return "-"
    if in_levels:
        return f"{value} niveaux"
    return f"{value // 3600}:{value // 60 % 60:02d}:{value % 60:02d}"


def slot_rows(status: GameStatus) -> list[tuple[str, str, str, str]]:
    """Lignes du tableau des slots d'un jeu : slot, PC, Vita, plus avancé.

    Args:
        status: État du jeu.

    Returns:
        Une ligne par slot.
    """
    labels = {"same": "identiques", "pc": "PC", "vita": "Vita"}
    name = "Sauvegarde" if status.in_levels else "Slot {}"
    return [
        (
            name.format(state.slot),
            format_progress(state.pc, status.in_levels),
            format_progress(state.vita, status.in_levels),
            labels[state.newer],
        )
        for state in status.states
    ]


class VitaSyncWindow(tk.Tk):
    """Fenêtre principale."""

    def __init__(self, session: service.Session) -> None:
        """Construit la fenêtre.

        Args:
            session: Session ouverte (configuration de la Vita, de Steam et stockage).
        """
        super().__init__()
        self.session = session
        self.games: dict[str, GameManifest] = {
            game_id: game
            for game_id, game in builtin_manifests().items()
            if game.adapter in service.SUPPORTED_ADAPTERS
        }
        self.statuses: dict[str, GameStatus] = {}
        self.results: queue.Queue[Callable[[], None]] = queue.Queue()
        self.busy = False

        self.title(f"VitaSync {__version__}")
        self.geometry("760x560")
        self.minsize(600, 440)
        self._build()
        self.after(POLL_MS, self._poll)

    # --- Construction -----------------------------------------------------

    def _build(self) -> None:
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        vita = self.session.vita
        ttk.Label(top, text=f"Vita : {vita.host}:{vita.port}").pack(side="left")
        self.refresh_button = ttk.Button(top, text="Actualiser", command=self.refresh)
        self.refresh_button.pack(side="right")
        self.sync_button = ttk.Button(top, text="Synchroniser", command=self.sync_selected)
        self.sync_button.pack(side="right", padx=6)

        self.game_list = ttk.Treeview(
            self, columns=("state",), show="tree headings", height=len(self.games) or 1
        )
        self.game_list.heading("#0", text="Jeu")
        self.game_list.heading("state", text="État")
        self.game_list.column("#0", width=260)
        for game_id, game in self.games.items():
            self.game_list.insert("", "end", iid=game_id, text=game.name, values=("?",))
        self.game_list.pack(fill="x", padx=8)
        self.game_list.bind("<<TreeviewSelect>>", lambda _event: self._show_slots())

        self.slot_list = ttk.Treeview(
            self, columns=("pc", "vita", "newer"), show="tree headings", height=8
        )
        for column, text in (("#0", ""), ("pc", "PC"), ("vita", "Vita"), ("newer", "Plus avancé")):
            self.slot_list.heading(column, text=text)
        self.slot_list.pack(fill="both", expand=True, padx=8, pady=8)

        self.log = tk.Text(self, height=8, state="disabled", wrap="word")
        self.log.pack(fill="x", padx=8, pady=(0, 8))
        self.write_log("Ouvre l'appli VitaSync sur la Vita, puis clique sur Actualiser.")

    # --- Journal et tâches de fond ----------------------------------------

    def write_log(self, text: str) -> None:
        """Ajoute une ligne au journal en bas de la fenêtre."""
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.refresh_button.configure(state=state)
        self.sync_button.configure(state=state)
        self.configure(cursor="watch" if busy else "")

    def _run(self, work: Callable[[], Any], done: Callable[[Any], None]) -> None:
        """Lance ``work`` en tâche de fond, puis ``done(résultat)`` dans la fenêtre."""
        if self.busy:
            return
        self._set_busy(True)

        def target() -> None:
            try:
                value = work()
            except service.USER_ERRORS as exc:
                message = str(exc)
                self.results.put(lambda: self._failed(message))
            else:
                self.results.put(lambda: done(value))

        threading.Thread(target=target, daemon=True).start()

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        self.write_log(f"Erreur : {message}")

    def _poll(self) -> None:
        while not self.results.empty():
            self.results.get()()
        self.after(POLL_MS, self._poll)

    # --- Actions ------------------------------------------------------------

    def refresh(self) -> None:
        """Interroge la Vita et met à jour l'état de chaque jeu."""
        self.write_log("Lecture des sauvegardes...")

        def work() -> dict[str, GameStatus | str]:
            found: dict[str, GameStatus | str] = {}
            with VitaFtpClient(self.session.vita) as ftp:
                for game_id, game in self.games.items():
                    try:
                        found[game_id] = service.game_status(self.session, ftp, game)
                    except service.USER_ERRORS as exc:
                        found[game_id] = str(exc)
            return found

        self._run(work, self._refreshed)

    def _refreshed(self, found: dict[str, GameStatus | str]) -> None:
        self._set_busy(False)
        for game_id, value in found.items():
            if isinstance(value, GameStatus):
                self.statuses[game_id] = value
                self.game_list.item(game_id, values=(value.summary,))
            else:
                self.statuses.pop(game_id, None)
                self.game_list.item(game_id, values=("Indisponible",))
                self.write_log(f"{self.games[game_id].name} : {value}")
        self.write_log("État mis à jour.")
        self._show_slots()

    def _selected(self) -> str | None:
        selection = self.game_list.selection()
        return selection[0] if selection else None

    def _show_slots(self) -> None:
        self.slot_list.delete(*self.slot_list.get_children())
        game_id = self._selected()
        if game_id is None or game_id not in self.statuses:
            return
        for name, pc, vita, newer in slot_rows(self.statuses[game_id]):
            self.slot_list.insert("", "end", text=name, values=(pc, vita, newer))

    def sync_selected(self) -> None:
        """Synchronise le jeu sélectionné, après confirmation."""
        game_id = self._selected()
        if game_id is None or game_id not in self.statuses:
            self.write_log("Choisis un jeu, après avoir cliqué sur Actualiser.")
            return
        status = self.statuses[game_id]
        if status.conflict:
            messagebox.showwarning("Conflit", status.conflict, parent=self)
            return
        if status.direction is None:
            self.write_log(f"{status.game.name} : déjà synchronisé.")
            return
        plan = service.describe_plan(status)
        question = (
            f"{status.game.name}\n{plan}\n\nUne copie de sécurité sera faite avant. Continuer ?"
        )
        if not messagebox.askyesno("Synchroniser", question, parent=self):
            return
        self.write_log(f"{status.game.name} : {plan}")
        direction = status.direction

        def work() -> list[str]:
            with VitaFtpClient(self.session.vita) as ftp:
                result = service.transfer(self.session, ftp, status.game, direction, status.slots)
            return service.describe_result(status.game, direction, result)

        def done(lines: list[str]) -> None:
            self._set_busy(False)
            for line in lines:
                self.write_log(line)
            self.refresh()

        self._run(work, done)


def main() -> int:
    """Ouvre la fenêtre de VitaSync.

    Returns:
        0 à la fermeture de la fenêtre, 1 si la configuration est absente.
    """
    try:
        session = service.open_session()
    except service.USER_ERRORS as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("VitaSync", f"Configuration impossible à lire :\n{exc}")
        root.destroy()
        return 1
    VitaSyncWindow(session).mainloop()
    return 0
