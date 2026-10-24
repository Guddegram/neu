"""Rumänien-VPN – kleine Mac-App: ein Knopf für Tor mit Ausgang in Rumänien.

Uses the same code as `neuvpn tor` (start/stop, macOS proxy, IP check).
Closing the window switches the VPN off and restores the proxy settings.
"""

import json
import os
import queue
import signal
import sys
import threading
import tkinter as tk
from tkinter import ttk

from . import httpproxy, tor
from .config import default_data_dir

COUNTRY = "RO"  # default selection
# exactly these countries are offered, nothing else
COUNTRIES = {
    "RO": ("🇷🇴", "Rumänien"),
    "TR": ("🇹🇷", "Türkei"),
    "IN": ("🇮🇳", "Indien"),
    "AR": ("🇦🇷", "Argentinien"),
    "EC": ("🇪🇨", "Ecuador"),
}
_LABELS = {code: f"{flag}  {name}" for code, (flag, name) in COUNTRIES.items()}
_BY_LABEL = {label: code for code, label in _LABELS.items()}
SOCKS, HTTP, CONTROL = tor.DEFAULT_SOCKS_PORT, tor.DEFAULT_HTTP_PORT, tor.DEFAULT_CONTROL_PORT
WATCH_INTERVAL_MS = int(os.environ.get("NEUVPN_GUI_WATCH_MS", "30000"))
COLORS = {"off": "#8e8e93", "connecting": "#ff9f0a", "on": "#30d158", "error": "#ff453a"}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.paths = tor.TorPaths(default_data_dir() / "tor")
        self.events: queue.Queue = queue.Queue()
        self.state = "off"
        self.info: dict = {}
        self.busy = False
        self.cancelled = False
        self.watching = False
        self.sharing = False  # copy of the checkbox, safe to read from worker threads
        self.active_country = os.environ.get("NEUVPN_GUI_COUNTRY", COUNTRY).upper()
        if self.active_country not in COUNTRIES:
            self.active_country = COUNTRY
        self.status_file = os.environ.get("NEUVPN_GUI_STATUS")

        root.title("Rumänien-VPN")
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=24)
        frame.grid()
        ttk.Label(frame, text="🌍  Länder-VPN", font=("Helvetica", 20, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 12))
        self.country_var = tk.StringVar(value=_LABELS[self.active_country])
        self.country_box = ttk.Combobox(frame, textvariable=self.country_var, state="readonly",
                                        values=list(_LABELS.values()), width=20,
                                        font=("Helvetica", 14))
        self.country_box.grid(row=1, column=0, columnspan=2, pady=(0, 12))
        self.country_box.bind("<<ComboboxSelected>>", lambda _e: self.pick_country())
        self.dot = tk.Canvas(frame, width=18, height=18, highlightthickness=0)
        self.dot.grid(row=2, column=0, sticky="e", padx=(0, 8))
        self.title = ttk.Label(frame, font=("Helvetica", 15, "bold"))
        self.title.grid(row=2, column=1, sticky="w")
        self.detail = ttk.Label(frame, justify="center", wraplength=320)
        self.detail.grid(row=3, column=0, columnspan=2, pady=(6, 16))
        self.button = ttk.Button(frame, width=22, command=self.toggle)
        self.button.grid(row=4, column=0, columnspan=2, ipady=8)
        self.newip = ttk.Button(frame, text="Neue IP", width=22, command=self.new_ip)
        self.newip.grid(row=5, column=0, columnspan=2, pady=(8, 0))
        self.share = tk.BooleanVar(value=os.environ.get("NEUVPN_GUI_SHARE") == "1")
        self.share_box = ttk.Checkbutton(frame, text="Handy im selben WLAN mitnutzen",
                                         variable=self.share)
        self.share_box.grid(row=6, column=0, columnspan=2, pady=(16, 0))
        self.share_info = ttk.Label(frame, justify="center", wraplength=320, foreground="#636366")
        self.share_info.grid(row=7, column=0, columnspan=2, pady=(6, 0))

        root.protocol("WM_DELETE_WINDOW", self.quit)
        # macOS: Cmd+Q, "Beenden" im Dock/Menü and logout go through ::tk::mac::Quit
        root.createcommand("::tk::mac::Quit", self.quit)
        signal.signal(signal.SIGTERM, lambda *_: self.events.put(("quit", None)))
        self.render()
        self.poll_job = root.after(100, self.poll)
        self.watch_job = root.after(WATCH_INTERVAL_MS, self.watch)

        if tor.recover_system_proxy(self.paths):
            self.info = {"note": "Proxy-Einstellungen vom letzten Mal wurden zurückgesetzt."}
        if tor.running_pid(self.paths):  # already running (e.g. started in the terminal)
            self.set_state("connecting", {"percent": 100})
            self.run(self._check_worker)
        elif os.environ.get("NEUVPN_GUI_AUTOSTART") == "1":
            root.after(500, self.toggle)
        self.write_status(self.state)

    # ---- state & UI ----------------------------------------------------

    def set_state(self, state: str, info: dict | None = None) -> None:
        self.state = state
        self.info = info or {}
        self.render()
        self.write_status(state)

    def write_status(self, state: str) -> None:
        """For automated tests (NEUVPN_GUI_STATUS): current state as JSON."""
        if self.status_file:
            tmp = self.status_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"state": state, **self.info}, fh)
            os.replace(tmp, self.status_file)

    def render(self) -> None:
        state, info = self.state, self.info
        self.dot.delete("all")
        self.dot.create_oval(2, 2, 16, 16, fill=COLORS[state], outline="")
        active_name = COUNTRIES[self.active_country][1]
        if state == "off":
            title, detail, button = "Aus", "Du surfst mit deiner normalen IP.", "Einschalten"
        elif state == "connecting":
            title = "Verbinde …"
            detail = info.get("message") or f"Verbindungsaufbau {info.get('percent', 0)} %"
            button = "Abbrechen"
        elif state == "on":
            code = info.get("country")
            where = COUNTRIES.get(code, ("", code or "?"))[1]
            city = f", {info['city']}" if info.get("city") else ""
            title = f"An – {where}"
            detail = (f"Öffentliche IP: {info.get('ip', '?')}{city}\n"
                      f"Safari, Chrome & Co. laufen über {where}.")
            if code != self.active_country:
                detail += "\nStandort weicht noch ab – wird automatisch korrigiert …"
            button = "Ausschalten"
        else:
            title, detail, button = "Fehler", info.get("message", ""), "Nochmal versuchen"
        if info.get("note"):
            detail += f"\n{info['note']}"
        self.title.configure(text=title)
        self.detail.configure(text=detail)
        self.button.configure(text=button, state="disabled" if self.busy and state != "connecting"
                              else "normal")
        self.newip.configure(text=f"Neue IP ({active_name})",
                             state="normal" if state == "on" and not self.busy else "disabled")
        self.share_box.configure(state="normal" if state in ("off", "error") else "disabled")
        self.country_box.configure(state="readonly" if state in ("off", "error") and not self.busy
                                   else "disabled")
        lan = info.get("lan")
        self.share_info.configure(text=(
            f"Am Handy: WLAN › Proxy › Manuell\nServer {lan}   Port {HTTP}" if lan else ""))

    def poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "quit":
                    self.quit()
                    return
                if kind == "state":
                    self.set_state(*payload)
                elif kind == "done":
                    self.busy = False
                    self.render()
        except queue.Empty:
            pass
        self.poll_job = self.root.after(100, self.poll)

    def post(self, state: str, info: dict | None = None) -> None:
        self.events.put(("state", (state, info)))

    def run(self, worker) -> None:
        self.busy = True
        self.render()

        def wrapper():
            try:
                worker()
            except Exception as exc:  # never leave the window stuck in "Verbinde …"
                self.post("error", {"message": f"Unerwarteter Fehler: {exc}"[:300]})
            finally:
                self.events.put(("done", None))

        threading.Thread(target=wrapper, daemon=True).start()

    # ---- actions -------------------------------------------------------

    def pick_country(self) -> None:
        if self.state in ("off", "error") and not self.busy:
            self.active_country = _BY_LABEL.get(self.country_var.get(), COUNTRY)
        else:  # locked while connected; put the selection back
            self.country_var.set(_LABELS[self.active_country])
        self.render()

    def toggle(self) -> None:
        if self.state in ("off", "error"):
            self.sharing = self.share.get()
            self.run(self._start_worker)
        elif self.state == "connecting":
            self.cancelled = True
            tor.stop(self.paths)  # start() notices that tor ended
        else:
            self.run(self._stop_worker)

    def new_ip(self) -> None:
        def worker():
            try:
                tor.new_identity(self.paths, CONTROL)
            except (tor.TorError, OSError):
                pass
            self._check_worker()
        self.run(worker)

    def _start_worker(self) -> None:
        self.cancelled = False
        country = self.active_country
        name = COUNTRIES[country][1]
        self.post("connecting", {"percent": 0, "message": f"Prüfe Server in {name} …"})
        exits = tor.exit_count(country)  # honest check: None = unknown, 0 = impossible
        if exits == 0:
            self.post("error", {"message": (
                f"In {name} gibt es im Tor-Netz gerade keine Ausgangs-Server – eine "
                f"{name}-IP ist deshalb aktuell nicht möglich. Bitte anderes Land wählen.")})
            return
        self.post("connecting", {"percent": 0})
        try:
            torrc = tor.build_torrc(self.paths, country, SOCKS, HTTP, CONTROL, share=self.sharing)
            tor.start(
                self.paths, torrc,
                progress=lambda p: self.post("connecting", {"percent": p}),
                on_restart=lambda p: self.post("connecting", {
                    "message": f"Hängt bei {p} % – neuer Versuch …"}),
            )
        except (tor.TorError, OSError) as exc:
            if self.cancelled:
                self.post("off")
            else:
                self.post("error", {"message": str(exc)[:300]})
            return
        if tor.is_mac() and not tor.set_mac_system_proxy(self.paths, SOCKS, HTTP, enable=True):
            tor.stop(self.paths)
            self.post("error", {"message": "Mac-Proxy konnte nicht eingeschaltet werden "
                                           "(Passwort abgebrochen?)."})
            return
        self._check_worker()

    def _check_worker(self) -> None:
        info: dict = {}
        if tor.torrc_ports(self._torrc()).get("socks", ("",))[0] == "0.0.0.0":
            lan = tor.lan_addresses()
            info["lan"] = lan[0] if lan else "?"
        # check like a website does; exits located elsewhere are excluded automatically
        ip, country, city = tor.ensure_exit_country(self.paths, self.active_country,
                                                    SOCKS, CONTROL)
        if ip:
            info.update(ip=ip, country=country, city=city)
        else:
            info.update(note="Standort konnte gerade nicht geprüft werden.")
        if tor.running_pid(self.paths):
            self.post("on", info)

    def watch(self) -> None:
        """While on: re-check the exit regularly (Tor switches circuits every few minutes)."""
        if self.state == "on" and not self.busy and not self.watching:
            self.watching = True

            def worker():
                try:
                    self._check_worker()
                finally:
                    self.watching = False

            threading.Thread(target=worker, daemon=True).start()
        self.watch_job = self.root.after(WATCH_INTERVAL_MS, self.watch)

    def _torrc(self) -> str:
        try:
            return self.paths.torrc.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _stop_worker(self) -> None:
        self._switch_off()
        self.post("off")

    def _switch_off(self) -> None:
        if tor.is_mac() and self.paths.proxy_state.exists():
            tor.set_mac_system_proxy(self.paths, SOCKS, HTTP, enable=False)
        tor.stop(self.paths)

    def quit(self) -> None:
        if self.state != "off" or tor.running_pid(self.paths):
            self.title.configure(text="Schalte aus …")
            self.root.update()
            self._switch_off()
        self.write_status("closed")
        self.root.after_cancel(self.poll_job)
        self.root.after_cancel(self.watch_job)
        self.root.destroy()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == tor.HTTP_PROXY_FLAG:
        httpproxy.main(sys.argv[2:])  # helper process of the app (see tor._start_http_proxy)
        return
    root = tk.Tk()
    App(root)
    root.lift()
    root.attributes("-topmost", True)
    root.after(800, lambda: root.attributes("-topmost", False))
    root.mainloop()


if __name__ == "__main__":
    main()
