#!/usr/bin/env python3
"""
Diagnostic : lit l'entree ASIO de la SQ et affiche les niveaux en console.

Ne touche a rien d'autre : pas de serveur web, pas de sortie audio.
Si les niveaux bougent ici, l'entree ASIO fonctionne et le probleme est
dans l'interface web. S'ils restent a zero, le probleme est en amont.

    python test_asio.py
    python test_asio.py --device 35
"""

import argparse
import os
import sys
import time

os.environ["SD_ENABLE_ASIO"] = "1"

import numpy as np
import sounddevice as sd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", type=int, default=None, help="Index du peripherique ASIO")
    p.add_argument("--channels", type=int, default=32)
    p.add_argument("--samplerate", type=int, default=48000)
    p.add_argument("--seconds", type=int, default=30)
    args = p.parse_args()

    device = args.device
    if device is None:
        apis = sd.query_hostapis()
        for idx, dev in enumerate(sd.query_devices()):
            api = apis[dev["hostapi"]]["name"].upper()
            if "ASIO" in api and dev["max_input_channels"] >= 8:
                device = idx
                break
    if device is None:
        print("Aucun peripherique ASIO multicanal trouve.")
        return 1

    info = sd.query_devices(device)
    n = min(args.channels, info["max_input_channels"])
    print(f"Peripherique : [{device}] {info['name']}")
    print(f"Canaux lus   : {n}")
    print(f"Frequence    : {args.samplerate} Hz")
    print("\nParlez dans un micro. Ctrl+C pour arreter.\n")

    peaks = np.zeros(n, dtype=np.float32)
    frames_seen = [0]

    def cb(indata, frames, t, status):
        if status:
            print(f"  [status] {status}")
        nonlocal peaks
        peaks = np.maximum(peaks * 0.6, np.max(np.abs(indata[:, :n]), axis=0))
        frames_seen[0] += frames

    try:
        stream = sd.InputStream(
            device=device,
            channels=n,
            samplerate=args.samplerate,
            blocksize=512,
            dtype="float32",
            extra_settings=sd.AsioSettings(channel_selectors=list(range(n))),
            callback=cb,
        )
    except Exception as exc:
        print(f"Ouverture impossible : {exc}")
        print("\nSi le message parle de sample rate, verifiez que la SQ")
        print("et --samplerate sont sur la meme valeur.")
        return 1

    with stream:
        t0 = time.time()
        try:
            while time.time() - t0 < args.seconds:
                time.sleep(0.15)
                line = []
                for i in range(n):
                    v = peaks[i]
                    db = -120 if v < 1e-6 else 20 * np.log10(v)
                    if db < -60:
                        mark = "."
                    elif db < -30:
                        mark = "-"
                    elif db < -12:
                        mark = "+"
                    else:
                        mark = "#"
                    line.append(mark)
                loud = int(np.argmax(peaks))
                top = peaks[loud]
                top_db = -120 if top < 1e-6 else 20 * np.log10(top)
                sys.stdout.write(
                    f"\r{''.join(line)}   max: canal {loud + 1:2d} "
                    f"{top_db:6.1f} dB   blocs recus: {frames_seen[0] // 512:5d}"
                )
                sys.stdout.flush()
        except KeyboardInterrupt:
            pass

    print("\n")
    if frames_seen[0] == 0:
        print("AUCUN bloc audio recu : le flux ASIO ne tourne pas.")
    elif float(np.max(peaks)) < 1e-5:
        print("Blocs recus mais tous les canaux sont a zero.")
        print("Le flux ASIO tourne, mais la console n'envoie rien sur l'USB.")
        print("Verifiez Routing > Direct Out, et le patch I/O > USB B.")
    else:
        print("Signal detecte. L'entree ASIO fonctionne.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
