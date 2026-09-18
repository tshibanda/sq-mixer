#!/usr/bin/env python3
"""
SQ Mixer - surface de mixage pour Allen & Heath SQ sur Windows.

Lit les 32 canaux du driver ASIO de la SQ, applique une matrice de mixage
(gain / mute / pan / PFL), et renvoie :
  - un bus PRINCIPAL vers un peripherique virtuel (VB-Cable) que OBS capte
  - un bus CASQUE optionnel, avec ecoute PFL, sur la carte son du PC

Le PFL (solo) n'affecte JAMAIS le bus principal : on ne casse pas un direct
parce qu'on veut ecouter un micro.

Usage :
    python sq_mixer.py --list-devices
    python sq_mixer.py
    python sq_mixer.py --config ma_config.json --port 8770
"""

import argparse
import asyncio
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

# sounddevice livre deux DLL PortAudio : une avec ASIO, une sans. Celle sans
# ASIO est chargee par defaut. Sans cette ligne, la SQ n'apparait qu'en paires
# stereo MME/WASAPI et les 32 canaux restent inaccessibles.
# Doit imperativement etre defini AVANT l'import de sounddevice.
if os.environ.get("SD_DISABLE_ASIO") != "1":
    os.environ["SD_ENABLE_ASIO"] = "1"

import sounddevice as sd

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

# Une fois compile par PyInstaller, les ressources embarquees (ui.html) vivent
# dans un dossier temporaire, alors que la config et les presets doivent rester
# a cote de l'executable pour survivre aux mises a jour.
if getattr(sys, "frozen", False):
    RES_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(sys.executable).resolve().parent
else:
    RES_DIR = Path(__file__).resolve().parent
    DATA_DIR = RES_DIR

BASE_DIR = RES_DIR
PRESET_DIR = DATA_DIR / "presets"
DEFAULT_CONFIG = DATA_DIR / "config.json"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CHANNEL_NAMES = [
    # Patch USB B de la regie ICC (I/O > USB B, sockets 1 a 8)
    "Pasteur", "Lead", "Mode 0", "Mode",
    "Tyrios", "M1", "M2", "M3",
]


def default_config():
    return {
        # Noms de peripheriques, pas des index : les index changent
        # d'une session a l'autre. Une sous-chaine suffit.
        "input_device": None,       # ex: "SQ ASIO Driver"
        "main_device": None,        # ex: "CABLE Input"
        "monitor_device": None,     # ex: "Casque", optionnel
        "samplerate": 48000,
        "blocksize": 512,
        "input_channels": 32,
        "master_gain_db": 0.0,
        "master_mute": False,
        "monitor_gain_db": -6.0,
        "limiter_ceiling_db": -1.0,
        # Charge automatiquement ce preset au demarrage, au lieu de partir
        # tout MUTE. Laisser vide ("") pour revenir au comportement prudent.
        "default_preset": "Culte dimanche",
        "channels": [
            {
                "name": DEFAULT_CHANNEL_NAMES[i] if i < len(DEFAULT_CHANNEL_NAMES) else f"Canal {i + 1}",
                "gain_db": -120.0,
                "mute": True,
                "pfl": False,
                # Centre par defaut : une source mono doit sortir des deux
                # cotes. Ne panoramiquez que les vraies paires stereo.
                "pan": 0.0,
                "link": False,
            }
            for i in range(32)
        ],
    }


def load_config(path):
    cfg = default_config()
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"config.json illisible ({exc}). Configuration par defaut utilisee.")
            return cfg
        for key, value in user.items():
            if key == "channels" and isinstance(value, list):
                for i, ch in enumerate(value[: len(cfg["channels"])]):
                    cfg["channels"][i].update(ch)
            else:
                cfg[key] = value
    return cfg


def save_config(cfg, path):
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Utilitaires audio
# ---------------------------------------------------------------------------

def db_to_lin(db):
    if db <= -119.0:
        return 0.0
    return float(10.0 ** (db / 20.0))


def lin_to_db(lin):
    if lin <= 1e-7:
        return -120.0
    return float(20.0 * math.log10(lin))


class RingBuffer:
    """Tampon circulaire stereo entre le callback d'entree et celui de sortie.

    L'horloge de la SQ et celle du peripherique virtuel derivent lentement.
    On absorbe la derive en laissant le remplissage flotter autour d'une cible,
    et en jetant un bloc si on deborde.
    """

    def __init__(self, capacity_frames):
        self.capacity = int(capacity_frames)
        self.buf = np.zeros((self.capacity, 2), dtype=np.float32)
        self.write = 0
        self.read = 0
        self.lock = threading.Lock()
        self.underruns = 0
        self.overruns = 0

    @property
    def fill(self):
        with self.lock:
            return (self.write - self.read) % self.capacity

    def push(self, block):
        n = len(block)
        with self.lock:
            free = self.capacity - ((self.write - self.read) % self.capacity) - 1
            if n > free:
                # On avance la lecture : on prefere perdre du vieux son
                # qu'accumuler de la latence.
                self.read = (self.read + (n - free)) % self.capacity
                self.overruns += 1
            end = self.write + n
            if end <= self.capacity:
                self.buf[self.write:end] = block
            else:
                cut = self.capacity - self.write
                self.buf[self.write:] = block[:cut]
                self.buf[: end - self.capacity] = block[cut:]
            self.write = end % self.capacity

    def pop(self, n, out):
        with self.lock:
            avail = (self.write - self.read) % self.capacity
            take = min(n, avail)
            if take < n:
                self.underruns += 1
            end = self.read + take
            if end <= self.capacity:
                out[:take] = self.buf[self.read:end]
            else:
                cut = self.capacity - self.read
                out[:cut] = self.buf[self.read:]
                out[cut:take] = self.buf[: end - self.capacity]
            if take < n:
                out[take:] = 0.0
            self.read = end % self.capacity


# ---------------------------------------------------------------------------
# Moteur
# ---------------------------------------------------------------------------

class MixerEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.n_in = int(cfg["input_channels"])
        self.samplerate = int(cfg["samplerate"])
        self.blocksize = int(cfg["blocksize"])

        self.main_matrix = np.zeros((self.n_in, 2), dtype=np.float32)
        self.mon_matrix = np.zeros((self.n_in, 2), dtype=np.float32)
        self._main_prev = self.main_matrix
        self._mon_prev = self.mon_matrix

        self.master_lin = np.float32(0.0)
        self.monitor_lin = np.float32(0.0)
        self.ceiling = np.float32(db_to_lin(cfg.get("limiter_ceiling_db", -1.0)))

        self.peaks = np.zeros(self.n_in, dtype=np.float32)
        self.main_peak = np.zeros(2, dtype=np.float32)
        self.limiter_active = False

        # ~500 ms de marge : la latence n'a aucune importance en streaming,
        # la stabilite si.
        cap = max(8192, self.samplerate // 2)
        self.main_ring = RingBuffer(cap)
        self.mon_ring = RingBuffer(cap)

        self._ramp = np.linspace(0.0, 1.0, 4096, dtype=np.float32)
        self.in_stream = None
        self.main_stream = None
        self.mon_stream = None
        self.running = False
        self.last_error = None
        self.tone = False
        self.in_status = 0
        self.callback_errors = 0
        self.write_errors = 0
        self._threads = []

        self.rebuild_matrices()

    # -- matrices -----------------------------------------------------------

    def rebuild_matrices(self):
        """Recalcule les matrices de gain. Appele depuis le thread web.

        On construit un nouveau tableau puis on remplace la reference : les
        callbacks audio lisent toujours une matrice coherente, sans verrou.
        """
        cfg = self.cfg
        main = np.zeros((self.n_in, 2), dtype=np.float32)
        mon = np.zeros((self.n_in, 2), dtype=np.float32)
        any_pfl = any(ch.get("pfl") for ch in cfg["channels"][: self.n_in])

        for i, ch in enumerate(cfg["channels"][: self.n_in]):
            gain = db_to_lin(float(ch.get("gain_db", -120.0)))
            pan = float(np.clip(ch.get("pan", 0.0), -1.0, 1.0))
            # Loi de panoramique a puissance constante (-3 dB au centre)
            angle = (pan + 1.0) * math.pi / 4.0
            gl, gr = math.cos(angle), math.sin(angle)

            if not ch.get("mute", False):
                main[i, 0] = gain * gl
                main[i, 1] = gain * gr

            if any_pfl:
                # PFL : ecoute pre-fader, pre-mute, mono centre
                if ch.get("pfl"):
                    mon[i, 0] = 0.7071
                    mon[i, 1] = 0.7071
            else:
                mon[i] = main[i]

        self.main_matrix = main
        self.mon_matrix = mon
        self.master_lin = np.float32(
            0.0 if cfg.get("master_mute") else db_to_lin(float(cfg.get("master_gain_db", 0.0)))
        )
        self.monitor_lin = np.float32(db_to_lin(float(cfg.get("monitor_gain_db", -6.0))))
        self.ceiling = np.float32(db_to_lin(float(cfg.get("limiter_ceiling_db", -1.0))))

    def _mix(self, indata, matrix, prev, frames):
        out = indata @ matrix
        if prev is not matrix:
            old = indata @ prev
            if frames > len(self._ramp):
                self._ramp = np.linspace(0.0, 1.0, frames, dtype=np.float32)
            r = self._ramp[:frames]
            if len(r) != frames:
                r = np.linspace(0.0, 1.0, frames, dtype=np.float32)
            r = r[:, None]
            out = old * (1.0 - r) + out * r
        return out

    # -- callbacks ----------------------------------------------------------

    def _input_callback(self, indata, frames, time_info, status):
        try:
            if status:
                self.in_status += 1

            data = indata[:, : self.n_in]
            self.peaks = np.max(np.abs(data), axis=0)

            main_m, mon_m = self.main_matrix, self.mon_matrix
            main = self._mix(data, main_m, self._main_prev, frames)
            mon = self._mix(data, mon_m, self._mon_prev, frames)
            self._main_prev, self._mon_prev = main_m, mon_m

            main *= self.master_lin
            peak = float(np.max(np.abs(main))) if main.size else 0.0
            if peak > self.ceiling:
                main *= self.ceiling / peak
                self.limiter_active = True
            else:
                self.limiter_active = False
            self.main_peak = np.max(np.abs(main), axis=0)

            mon *= self.monitor_lin
            np.clip(mon, -1.0, 1.0, out=mon)

            self.main_ring.push(np.ascontiguousarray(main, dtype=np.float32))
            if self.mon_stream is not None:
                self.mon_ring.push(np.ascontiguousarray(mon, dtype=np.float32))
        except Exception as exc:
            # Une exception non capturee ici tuerait le flux en silence.
            self.last_error = f"callback entree : {exc}"
            self.callback_errors += 1

    def _writer(self, stream, ring, name):
        """Ecriture bloquante vers la sortie, dans un thread dedie.

        Plus robuste qu'un callback : si un bloc met trop de temps a arriver,
        on ecrit du silence au lieu de laisser le flux mourir.
        """
        block = np.zeros((self.blocksize, 2), dtype=np.float32)
        phase = 0
        while self.running:
            try:
                if self.tone and name == "principale":
                    # Court-circuite tout le mixage : si OBS entend ceci,
                    # le chemin de sortie est bon et le probleme est ailleurs.
                    n = np.arange(self.blocksize, dtype=np.float32) + phase
                    sig = 0.2 * np.sin(2 * np.pi * 1000.0 * n / self.samplerate)
                    block[:, 0] = sig
                    block[:, 1] = sig
                    phase += self.blocksize
                else:
                    ring.pop(self.blocksize, block)
                stream.write(block)
            except Exception as exc:
                self.last_error = f"sortie {name} : {exc}"
                self.write_errors += 1
                time.sleep(0.05)

    # -- cycle de vie -------------------------------------------------------

    def start(self):
        cfg = self.cfg
        extra = None
        try:
            dev_info = sd.query_devices(cfg["input_device"], "input")
            api = sd.query_hostapis(dev_info["hostapi"])["name"]
            if "ASIO" in api.upper():
                extra = sd.AsioSettings(channel_selectors=list(range(self.n_in)))
        except Exception:
            pass

        self.in_stream = sd.InputStream(
            device=cfg["input_device"],
            channels=self.n_in,
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            dtype="float32",
            latency="low",
            extra_settings=extra,
            callback=self._input_callback,
        )

        self.main_stream = sd.OutputStream(
            device=cfg["main_device"],
            channels=2,
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            dtype="float32",
        )

        if cfg.get("monitor_device") is not None:
            self.mon_stream = sd.OutputStream(
                device=cfg["monitor_device"],
                channels=2,
                samplerate=self.samplerate,
                blocksize=self.blocksize,
                dtype="float32",
            )

        self.in_stream.start()
        self.main_stream.start()
        if self.mon_stream is not None:
            self.mon_stream.start()
        self.running = True

        self._threads = [
            threading.Thread(
                target=self._writer, args=(self.main_stream, self.main_ring, "principale"),
                daemon=True, name="sq-writer-main",
            )
        ]
        if self.mon_stream is not None:
            self._threads.append(
                threading.Thread(
                    target=self._writer, args=(self.mon_stream, self.mon_ring, "casque"),
                    daemon=True, name="sq-writer-mon",
                )
            )
        for t in self._threads:
            t.start()

    def stop(self):
        self.running = False
        time.sleep(0.1)
        for stream in (self.in_stream, self.main_stream, self.mon_stream):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self.running = False

    def meters(self):
        return {
            "channels": [round(lin_to_db(v), 1) for v in self.peaks],
            "main": [round(lin_to_db(v), 1) for v in self.main_peak],
            "limiter": self.limiter_active,
            "underruns": self.main_ring.underruns,
            "overruns": self.main_ring.overruns,
            "fill_ms": round(self.main_ring.fill / self.samplerate * 1000.0, 1),
        }


# ---------------------------------------------------------------------------
# Peripheriques
# ---------------------------------------------------------------------------

def list_devices():
    apis = sd.query_hostapis()
    print("\nPeripheriques audio detectes\n" + "=" * 70)
    for idx, dev in enumerate(sd.query_devices()):
        api = apis[dev["hostapi"]]["name"]
        io = []
        if dev["max_input_channels"]:
            io.append(f"in:{dev['max_input_channels']}")
        if dev["max_output_channels"]:
            io.append(f"out:{dev['max_output_channels']}")
        flag = "  <-- SQ" if "SQ" in dev["name"].upper() else ""
        print(f"[{idx:3d}] {api:<12} {dev['name'][:42]:<42} {' '.join(io)}{flag}")
    print("=" * 70)
    print("Pour la SQ, choisissez la ligne ASIO (32 entrees).")
    print("Pour la sortie vers OBS, choisissez CABLE Input (VB-Audio Virtual Cable).\n")


def resolve_device(spec, kind, label):
    """Convertit un nom de peripherique en index, au moment du demarrage.

    Les index PortAudio changent d'une session a l'autre selon les
    peripheriques presents. Les enregistrer dans config.json revient a
    envoyer l'audio au hasard : on resout donc par nom a chaque lancement.
    """
    devices = sd.query_devices()
    apis = sd.query_hostapis()
    key = "max_input_channels" if kind == "input" else "max_output_channels"

    if isinstance(spec, int):
        if not 0 <= spec < len(devices):
            print(f"{label} : index {spec} hors plage.")
            return None
        dev = devices[spec]
        if dev[key] < 1:
            print(f"{label} : [{spec}] {dev['name']} n'a pas d'{kind}.")
            return None
        return spec

    if not isinstance(spec, str):
        return None

    needle = spec.upper()
    cands = []
    for idx, dev in enumerate(devices):
        if dev[key] < 1 or needle not in dev["name"].upper():
            continue
        api = apis[dev["hostapi"]]["name"].upper()
        if kind == "input":
            rank = 0 if "ASIO" in api else 3
        else:
            rank = 0 if "WASAPI" in api else (1 if "DIRECTSOUND" in api else 2)
        cands.append((rank, -dev[key], idx))

    if not cands:
        print(f"{label} : aucun peripherique nomme \"{spec}\" n'est present.")
        return None

    cands.sort()
    idx = cands[0][2]
    dev = devices[idx]
    api = apis[dev["hostapi"]]["name"]
    print(f"{label} : [{idx}] {dev['name']} ({api})")
    return idx


def autodetect(cfg):
    """Renseigne les NOMS des peripheriques si la config est vide."""
    apis = sd.query_hostapis()
    devices = sd.query_devices()

    if not any("ASIO" in a["name"].upper() for a in apis):
        print("Aucune API ASIO chargee par PortAudio.")
        print("Verifiez que sounddevice est en version 0.5.1 ou superieure :")
        print("    pip install --upgrade sounddevice")
        return cfg

    if cfg.get("input_device") is None:
        best = None
        for idx, dev in enumerate(devices):
            api = apis[dev["hostapi"]]["name"].upper()
            if "ASIO" in api and dev["max_input_channels"] >= 8:
                name = dev["name"].upper()
                score = 0 if ("SQ" in name or "ALLEN" in name) else 1
                cand = (score, -dev["max_input_channels"], idx, dev)
                if best is None or cand < best:
                    best = cand
        if best is not None:
            dev = best[3]
            cfg["input_device"] = dev["name"]
            cfg["input_channels"] = min(cfg["input_channels"], dev["max_input_channels"])
            print(f"Entree detectee : {dev['name']} ({cfg['input_channels']} canaux)")

    if cfg.get("main_device") is None:
        for dev in devices:
            if dev["max_output_channels"] >= 2 and "CABLE INPUT" in dev["name"].upper():
                cfg["main_device"] = "CABLE Input"
                print("Sortie OBS detectee : CABLE Input")
                break

    return cfg


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def apply_preset(engine, name):
    """Charge le preset `name` dans engine.cfg. Renvoie False s'il n'existe pas."""
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    for i, ch in enumerate(data.get("channels", [])[: engine.n_in]):
        engine.cfg["channels"][i].update(ch)
    engine.cfg["master_gain_db"] = data.get("master_gain_db", 0.0)
    engine.cfg["monitor_gain_db"] = data.get("monitor_gain_db", -6.0)
    engine.rebuild_matrices()
    return True


# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------

def build_app(engine, config_path):
    app = FastAPI(title="SQ Mixer")
    PRESET_DIR.mkdir(exist_ok=True)

    @app.get("/")
    def index():
        return FileResponse(RES_DIR / "ui.html")

    @app.get("/api/state")
    def state():
        return {
            "channels": engine.cfg["channels"][: engine.n_in],
            "master_gain_db": engine.cfg["master_gain_db"],
            "master_mute": engine.cfg["master_mute"],
            "monitor_gain_db": engine.cfg["monitor_gain_db"],
            "n_in": engine.n_in,
            "running": engine.running,
            "samplerate": engine.samplerate,
            "monitor": engine.mon_stream is not None,
            "presets": sorted(p.stem for p in PRESET_DIR.glob("*.json")),
        }

    @app.post("/api/channel/{index}")
    async def set_channel(index: int, payload: dict):
        if not 0 <= index < engine.n_in:
            return JSONResponse({"error": "canal hors plage"}, status_code=400)
        ch = engine.cfg["channels"][index]
        for key in ("name", "gain_db", "mute", "pfl", "pan", "link"):
            if key in payload:
                ch[key] = payload[key]
        if ch.get("link") and index % 2 == 0 and index + 1 < engine.n_in:
            partner = engine.cfg["channels"][index + 1]
            partner["gain_db"] = ch["gain_db"]
            partner["mute"] = ch["mute"]
            partner["link"] = True
        engine.rebuild_matrices()
        return {"ok": True, "channel": ch}

    @app.post("/api/master")
    async def set_master(payload: dict):
        for key in ("master_gain_db", "master_mute", "monitor_gain_db"):
            if key in payload:
                engine.cfg[key] = payload[key]
        engine.rebuild_matrices()
        return {"ok": True}

    @app.post("/api/clear-pfl")
    async def clear_pfl():
        for ch in engine.cfg["channels"]:
            ch["pfl"] = False
        engine.rebuild_matrices()
        return {"ok": True}

    @app.post("/api/preset/{name}")
    async def save_preset(name: str):
        safe = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        if not safe:
            return JSONResponse({"error": "nom de preset vide"}, status_code=400)
        data = {
            "channels": engine.cfg["channels"][: engine.n_in],
            "master_gain_db": engine.cfg["master_gain_db"],
            "monitor_gain_db": engine.cfg["monitor_gain_db"],
        }
        (PRESET_DIR / f"{safe}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"ok": True, "name": safe}

    @app.post("/api/preset/{name}/load")
    async def load_preset(name: str):
        if not apply_preset(engine, name):
            return JSONResponse({"error": "preset introuvable"}, status_code=404)
        return {"ok": True}

    @app.websocket("/ws")
    async def meters_ws(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(engine.meters())
                await asyncio.sleep(0.05)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app


def main():
    parser = argparse.ArgumentParser(description="Surface de mixage pour Allen & Heath SQ")
    parser.add_argument("--list-devices", action="store_true", help="Lister les peripheriques audio")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Fichier de configuration")
    parser.add_argument("--port", type=int, default=8770, help="Port du serveur de controle")
    parser.add_argument("--host", default="0.0.0.0", help="Adresse d'ecoute")
    parser.add_argument("--tone", action="store_true",
                        help="Envoie une tonalite 1 kHz a la place du mix (diagnostic)")
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return 0

    config_path = Path(args.config)
    cfg = autodetect(load_config(config_path))

    if cfg.get("input_device") is None:
        print("Aucune entree ASIO SQ trouvee. Lancez : python sq_mixer.py --list-devices")
        print("puis renseignez input_device dans config.json.")
        return 1
    if cfg.get("main_device") is None:
        print("Aucune sortie trouvee. Installez VB-Audio Virtual Cable, ou renseignez")
        print("main_device dans config.json (voir --list-devices).")
        return 1

    save_config(cfg, config_path)

    # Resolution nom -> index, a chaque lancement.
    runtime = dict(cfg)
    runtime["input_device"] = resolve_device(cfg["input_device"], "input", "Entree ")
    runtime["main_device"] = resolve_device(cfg["main_device"], "output", "Sortie ")
    if runtime["input_device"] is None or runtime["main_device"] is None:
        print("\nPeripherique introuvable. Lancez : python sq_mixer.py --list-devices")
        return 1

    out_name = sd.query_devices(runtime["main_device"])["name"].upper()
    if "CABLE" not in out_name and "VB-AUDIO" not in out_name:
        print("\n*** ATTENTION : la sortie n'est pas un cable virtuel. ***")
        print(f"*** Le son ira vers \"{sd.query_devices(runtime['main_device'])['name']}\" ***")
        print("*** et non vers OBS. Corrigez main_device dans config.json. ***\n")

    engine = MixerEngine(runtime)

    default_preset = cfg.get("default_preset")
    if default_preset:
        if apply_preset(engine, default_preset):
            print(f"Preset charge au demarrage : {default_preset}")
        else:
            print(f"Preset par defaut introuvable : presets/{default_preset}.json (demarrage a MUTE)")

    try:
        engine.start()
    except Exception as exc:
        print(f"\nDemarrage audio impossible : {exc}\n")
        print("Verifiez que : la SQ est allumee et branchee en USB-B,")
        print("que la console et config.json sont sur la meme frequence,")
        print("et qu'aucune autre application ne tient le driver ASIO.")
        return 1

    engine.tone = args.tone

    in_dev = sd.query_devices(runtime["input_device"])
    out_dev = sd.query_devices(runtime["main_device"])
    print(f"\nMoteur audio demarre  -  {engine.samplerate} Hz, {engine.n_in} canaux")
    print(f"  entree  : [{runtime['input_device']}] {in_dev['name']}")
    print(f"  sortie  : [{runtime['main_device']}] {out_dev['name']}")
    if args.tone:
        print("\n  *** MODE TONALITE : 1 kHz envoye a la place du mix. ***")
        print("  *** Si OBS ne bouge pas, le probleme n'est pas dans le mixage. ***")

    # Verification que la sortie consomme reellement les donnees : c'est
    # exactement ce qui manquait quand le tampon saturait sans rien produire.
    time.sleep(1.0)
    if engine.main_ring.fill > engine.samplerate * 0.3:
        print("\n*** La sortie ne consomme pas les donnees. ***")
        if engine.last_error:
            print(f"    Derniere erreur : {engine.last_error}")
        print("    Essayez un autre main_device dans config.json.\n")

    try:
        import websockets  # noqa: F401
    except ImportError:
        print("\n*** ATTENTION : le paquet 'websockets' est absent. ***")
        print("Les VU-metres resteront figes. Corrigez avec :")
        print("    pip install websockets\n")

    def monitor_loop():
        while True:
            time.sleep(2.0)
            m = engine.meters()
            loud = max(range(engine.n_in), key=lambda i: engine.peaks[i])
            line = (
                f"\rtampon {m['fill_ms']:6.1f} ms | "
                f"sous-alim {m['underruns']:5d} | debord {m['overruns']:5d} | "
                f"max canal {loud + 1:2d} {m['channels'][loud]:6.1f} dB | "
                f"sortie {m['main'][0]:6.1f} dB"
            )
            if engine.callback_errors or engine.write_errors:
                line += f" | ERREURS {engine.callback_errors}/{engine.write_errors}"
            sys.stdout.write(line)
            sys.stdout.flush()
            if engine.last_error:
                print(f"\n    {engine.last_error}")
                engine.last_error = None

    threading.Thread(target=monitor_loop, daemon=True).start()

    print(f"Surface de controle   ->  http://localhost:{args.port}")
    print("Depuis une tablette sur le meme reseau, utilisez l'IP de ce PC.\n")

    app = build_app(engine, config_path)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        engine.stop()
    return 0


def _run():
    code = main()
    if getattr(sys, "frozen", False) and code != 0:
        input("\nUne erreur est survenue. Appuyez sur Entree pour fermer.")
    return code


if __name__ == "__main__":
    sys.exit(_run())
