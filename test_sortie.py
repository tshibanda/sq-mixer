#!/usr/bin/env python3
"""
Diagnostic de la SORTIE uniquement.

Envoie une tonalite de 1 kHz vers le peripherique choisi. Aucun rapport avec
la SQ : on teste seulement si Python arrive a ecrire dans VB-Cable et si OBS
le recoit.

    python test_sortie.py            -> teste toutes les sorties CABLE Input
    python test_sortie.py --device 42
"""

import argparse
import os
import sys
import time

os.environ["SD_ENABLE_ASIO"] = "1"

import numpy as np
import sounddevice as sd

SR = 48000
FREQ = 1000.0


def play(device, seconds=6.0):
    info = sd.query_devices(device)
    api = sd.query_hostapis(info["hostapi"])["name"]
    print(f"\n--- [{device}] {info['name']}  ({api}) ---")

    phase = [0.0]
    blocks = [0]
    fails = [0]

    def cb(outdata, frames, t, status):
        if status:
            fails[0] += 1
            print(f"    [status] {status}")
        n = np.arange(frames, dtype=np.float32)
        sig = 0.2 * np.sin(2 * np.pi * FREQ * (phase[0] + n) / SR)
        outdata[:, 0] = sig
        outdata[:, 1] = sig
        phase[0] += frames
        blocks[0] += 1

    try:
        with sd.OutputStream(
            device=device, channels=2, samplerate=SR,
            blocksize=512, dtype="float32", callback=cb,
        ):
            print(f"    Tonalite 1 kHz pendant {seconds:.0f} s. Regardez OBS.")
            time.sleep(seconds)
    except Exception as exc:
        print(f"    ECHEC : {exc}")
        return False

    print(f"    Blocs envoyes : {blocks[0]}   incidents : {fails[0]}")
    if blocks[0] == 0:
        print("    Le peripherique n'a jamais reclame de donnees.")
        return False
    print("    Sortie fonctionnelle du point de vue de Python.")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", type=int, default=None)
    p.add_argument("--seconds", type=float, default=6.0)
    args = p.parse_args()

    if args.device is not None:
        play(args.device, args.seconds)
        return 0

    apis = sd.query_hostapis()
    targets = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] < 2:
            continue
        if "CABLE INPUT" not in dev["name"].upper():
            continue
        api = apis[dev["hostapi"]]["name"].upper()
        rank = 0 if "WASAPI" in api else (1 if "DIRECTSOUND" in api else 2)
        targets.append((rank, idx))

    if not targets:
        print("Aucun peripherique CABLE Input trouve.")
        return 1

    targets.sort()
    print("Test de chaque API disponible pour CABLE Input.")
    print("Ouvrez OBS a cote et surveillez le metre de votre source.\n")
    for _, idx in targets:
        play(idx, args.seconds)

    print("\nNotez l'index sur lequel OBS a reagi, puis mettez-le")
    print("dans config.json comme 'main_device'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
