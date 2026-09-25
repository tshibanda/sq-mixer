# SQ Mixer

Surface de mixage pour Allen & Heath SQ-5 sous Windows. Prend les 32 canaux
ASIO de la console, les mixe dans un navigateur, et renvoie le résultat à OBS.

C'est le contournement de la limite des 8 canaux WDM du pilote Allen & Heath :
côté ASIO les 32 canaux sont là, il manquait une application pour les prendre.

```
SQ-5 (USB-B) ──ASIO 32 ch──▶ SQ Mixer ──stéréo──▶ VB-Cable ──▶ OBS
                                 │
                                 └──stéréo (PFL)──▶ casque du PC
```

## Fonctions

- 32 tranches : nom, fader, panoramique, mute
- **PFL** (écoute casque) qui n'affecte jamais le mix envoyé à OBS
- VU-mètre par canal avec maintien de crête, VU-mètre de sortie
- Limiteur de sécurité à −1 dBFS sur le bus principal
- Presets nommés, rechargeables en un clic
- Pilotable depuis un téléphone ou une tablette sur le même réseau
- Ligne d'état en console : tampon, coupures, niveaux

## Prérequis

1. **Pilote ASIO Allen & Heath** — https://www.allen-heath.com/hardware/sq/sq-5/resources/
2. **Python 3.10+** — https://www.python.org/downloads/ (cocher « Add python.exe to PATH »)
3. **VB-Audio Virtual Cable** — https://vb-audio.com/Cable/

## Installation

Placez le dossier dans un endroit stable (`C:\regie` par exemple), puis :

- `demarrer.bat` — lance tout ; crée l'environnement Python au premier appel
- `creer_raccourci.bat` — pose un raccourci sur le Bureau (une seule fois)
- `demarrage_auto.bat` — lance SQ Mixer automatiquement à l'ouverture de
  session Windows (raccourci dans le dossier Démarrage de l'utilisateur,
  sans droits admin). `demarrage_auto.bat /off` pour annuler
- `mettre_a_jour.bat` — récupère les dernières modifications depuis
  [GitHub](https://github.com/tshibanda/sq-mixer) ; à relancer après chaque
  mise à jour de l'application. Ne touche jamais `config.json` ni
  `presets\` (propres à cette machine)
- `construire_exe.bat` — produit `dist\SQ Mixer.exe`, autonome (optionnel)

L'interface s'ouvre sur `http://localhost:8770`.

Si la détection automatique échoue, copiez `config.exemple.json` en
`config.json` et ajustez les noms de périphériques. `python sq_mixer.py
--list-devices` les liste tous.

## Réglages côté console

Sans ces trois points, aucun signal n'arrivera sur l'USB :

- `Setup` > `Audio` > `Digital I/O` : **USB Sample Rate = 48 kHz**
- `Routing` > `Direct Out` : **Follow Mute**, **Follow DCA Mute** et
  **Follow Mute Group** sur **Off**
- `I/O` > `USB B` : patch des canaux vers les sends USB

## Dans OBS

Source **Capture audio (entrée)** > périphérique **CABLE Output
(VB-Audio Virtual Cable)**. Puis `Paramètres` > `Avancé` > `Audio` > 48 kHz.

Une seule source suffit : le mixage se fait dans l'application.

## Utilisation

| Geste | Effet |
|---|---|
| Double-clic sur un fader | Retour à 0 dB |
| Double-clic sur le panoramique | Retour au centre |
| MUTE | Coupe le canal dans le mix envoyé à OBS |
| PFL | Envoie le canal au casque seul, sans toucher au direct |
| Clic sur le nom | Renommer la tranche |

Au démarrage, le preset nommé par `default_preset` dans `config.json`
(« Culte dimanche » par défaut) est chargé automatiquement s'il existe.
S'il est absent, tout reste sur MUTE avec les faders à OFF — pour qu'aucun
son ne parte par surprise. Videz `default_preset` dans `config.json` pour
revenir à un démarrage toujours MUTE.

## Diagnostic

```
python sq_mixer.py --list-devices   # lister les périphériques
python sq_mixer.py --tone           # tonalité 1 kHz à la place du mix
python test_asio.py                 # niveaux des 32 canaux en console
python test_sortie.py               # tonalité vers chaque API de sortie
```

La ligne d'état doit afficher un tampon stable entre 10 et 40 ms avec des
compteurs de coupures à zéro. Si les coupures montent, augmentez `blocksize`
dans `config.json` (512 → 1024 → 2048). La latence n'a aucune importance en
streaming, la stabilité si.

## Limites connues

- L'ASIO est mono-client : si un autre logiciel tient le driver de la SQ,
  l'application ne démarrera pas
- Le mixage tourne en Python ; sur une machine chargée, montez le buffer
  plutôt que de chercher la latence basse
- Pas d'égaliseur ni de compresseur : faites-les sur la console

## Avant un direct

Lancez le mixeur, vérifiez que les VU-mètres bougent, chargez votre preset,
puis ouvrez OBS. Dans cet ordre. Ne fermez jamais la fenêtre noire : c'est
le moteur audio.
