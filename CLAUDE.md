# SQ Mixer

Surface de mixage pour console Allen & Heath SQ-5 sous Windows. Prend les
32 canaux ASIO de la console, applique un mixage pilotable depuis un
navigateur, et renvoie un bus stéréo vers OBS via un câble audio virtuel.

Usage réel : régie de culte à l'ICC (Impact Centre Chrétien). Le mixage se
fait en direct, pendant le service. Une panne pendant un direct n'est pas
rattrapable — la robustesse prime sur la latence ou l'élégance.

```
SQ-5 (USB-B) ──ASIO 32 ch──▶ sq_mixer.py ──stéréo──▶ VB-Cable ──▶ OBS
                                  │
                                  └──stéréo (PFL)──▶ casque du PC
```

## Pourquoi ce projet existe

Sous Windows, le pilote Allen & Heath n'expose que **4 paires stéréo en WDM**
(SQ 1&2, 3&4, 5&6, 7&8), alors que la couche ASIO donne accès aux 32 canaux.
OBS ne sait pas lire l'ASIO nativement, et le plugin `obs-asio` n'est plus
maintenu depuis OBS 30. Cette application fait le pont.

Sur macOS le problème ne se pose pas : la SQ est class-compliant Core Audio.

## Structure

| Fichier | Rôle |
|---|---|
| `sq_mixer.py` | Moteur audio + serveur FastAPI. Tout le back-end. |
| `ui.html` | Surface de contrôle, servie sur `/`. HTML/CSS/JS sans dépendance. |
| `config.json` | Périphériques et réglages globaux. **Noms**, pas d'index. |
| `presets/` | Presets de niveaux, un JSON par preset. |
| `test_asio.py` | Diagnostic entrée : affiche les niveaux des 32 canaux en console. |
| `test_sortie.py` | Diagnostic sortie : envoie une tonalité 1 kHz vers VB-Cable. |
| `demarrer.bat` | Lancement : venv, dépendances, moteur, navigateur. |
| `demarrage_auto.bat` | Pose/retire une tâche planifiée (`schtasks`, déclencheur `onlogon`) qui lance `demarrer.bat`. |
| `mettre_a_jour.bat` | Recale le dossier sur `origin/main` (GitHub) sans toucher `config.json`/`presets/`. |
| `construire_exe.bat` | Compile un exécutable autonome via PyInstaller. |
| `creer_raccourci.bat` | Crée le raccourci bureau. |

## Architecture du moteur

**Entrée** : `sd.InputStream` en callback sur le driver ASIO de la SQ.
Le callback calcule les crêtes par canal, applique deux matrices de gain
`(32, 2)` — une pour le bus principal, une pour le casque — puis pousse le
résultat dans un tampon circulaire.

**Sortie** : un thread dédié lit le tampon et écrit dans `sd.OutputStream`
en **mode bloquant**, sans callback.

**Matrices** : `rebuild_matrices()` construit un nouveau tableau puis remplace
la référence. Les callbacks lisent toujours une matrice cohérente, sans
verrou. Un fondu linéaire sur un bloc évite les clics au changement.

**PFL** : l'écoute casque est pré-fader et pré-mute, et n'affecte **jamais**
le bus envoyé à OBS. Comportement de console, volontaire.

## Pièges déjà rencontrés — ne pas les réintroduire

Ces points ont coûté plusieurs heures de débogage. Ils sont tous commentés
dans le code, mais les voici rassemblés.

**`SD_ENABLE_ASIO` avant l'import.** sounddevice livre deux DLL PortAudio ;
celle **sans** ASIO est chargée par défaut. Sans
`os.environ["SD_ENABLE_ASIO"] = "1"` placé avant `import sounddevice`,
aucune API ASIO n'apparaît et les 32 canaux sont invisibles.

**Jamais d'index de périphérique en configuration.** Les index PortAudio
changent d'une session à l'autre selon les périphériques présents. Un
`main_device: 42` qui désignait CABLE Input a fini par pointer sur
`SQ 7&8`, renvoyant tout l'audio dans la console. `config.json` stocke des
**noms**, résolus en index au démarrage par `resolve_device()`.

**Sortie en écriture bloquante, pas en callback.** Avec un callback de
sortie, toute exception tuait le flux silencieusement : le tampon saturait
à 500 ms et plus rien ne sortait, sans le moindre message. Le thread en
écriture bloquante est tolérant et diagnosticable.

**Le paquet `websockets` est requis.** FastAPI et uvicorn seuls ne gèrent
pas les WebSockets. Sans lui, les VU-mètres restent figés alors que les
faders fonctionnent — symptôme trompeur.

**L'ASIO est mono-client.** Si Reaper, FL Studio ou `test_asio.py` tient le
driver, le mixeur ne démarrera pas. ASIO4ALL et FL Studio ASIO sont installés
sur la machine de régie.

**Panoramique au centre par défaut.** Un premier jet plaçait les canaux
impairs à gauche et les pairs à droite pour préserver les paires stéréo.
Résultat : chaque source mono ne sortait que d'un côté, et une jauge sur
deux restait vide. Les sources sont mono par défaut.

**Toute exception dans un callback audio doit être capturée.** PortAudio
arrête le flux sans rien dire.

**Preset charge automatiquement au demarrage.** `main()` applique
`cfg["default_preset"]` (via `apply_preset()`) juste apres avoir construit
`MixerEngine`, avant `engine.start()` : le mix part directement sur les
niveaux du dernier preset enregistre, plutot que tout MUTE. Ce n'est plus
la demarche "rien ne part par surprise" du depart — choix explicite de
l'utilisateur pour ne plus recaler les niveaux a chaque lancement. Pour
revenir au demarrage prudent, vider `default_preset` dans `config.json`.

**Pas de raccourci dans le dossier Demarrage pour l'auto-lancement.**
Premiere version de `demarrage_auto.bat` : Windows (ou un antivirus) peut
desactiver silencieusement un raccourci du dossier Demarrage — aucune
erreur, aucun message, ca ne se voit meme pas au double-clic manuel du
script qui l'a cree. Ca s'est reproduit malgre un raccourci confirme
present. `demarrage_auto.bat` utilise desormais `schtasks` (declencheur
`onlogon`, `/rl limited`) : la tache a un historique consultable dans le
Planificateur de taches, contrairement a un raccourci.

## Réglages côté console (hors code, mais bloquants)

Ces réglages SQ conditionnent la présence de signal sur l'USB :

- `Setup` > `Audio` > `Digital I/O` : **USB Sample Rate = 48 kHz**, doit
  correspondre à `samplerate` dans `config.json`
- `Routing` > `Direct Out` : **Follow Mute**, **Follow DCA Mute** et
  **Follow Mute Group** sur **Off**, sinon rien ne part vers l'USB quand un
  canal est coupé en salle
- `I/O` > `USB B` : patch des canaux vers les sends USB. L'ordre défini ici
  est celui des tranches 1 à 32 de l'interface.

Patch actuel : 1 Pasteur, 2 Lead, 3 Mode 0, 4 Mode, 5 Tyrios, 6 M1, 7 M2,
8 M3. Les canaux 9 à 32 ne sont pas patchés.

## Conventions

- Python 3.10+, pas de framework au-delà de FastAPI/uvicorn/sounddevice/numpy
- Commentaires et messages utilisateur **en français, sans accents** dans les
  sorties console (l'encodage `cmd.exe` de Windows les mange)
- `ui.html` reste un fichier unique sans CDN : la régie doit fonctionner sans
  réseau le dimanche matin
- Pas de `localStorage` pour l'état partagé — le serveur est la source de vérité
- Aucun EQ ni compresseur dans l'application : la SQ le fait mieux

## Commandes

```bash
python sq_mixer.py                  # lancement normal
python sq_mixer.py --list-devices   # lister les périphériques
python sq_mixer.py --tone           # tonalité 1 kHz à la place du mix
python test_asio.py                 # diagnostic entrée
python test_sortie.py               # diagnostic sortie
```

La ligne d'état affichée toutes les deux secondes donne tampon, coupures,
canal le plus fort et niveau de sortie. Un tampon stable entre 10 et 40 ms
avec des compteurs à zéro signifie que le moteur est sain.

## Pistes non traitées

- Sauvegarde automatique de l'état à chaque modification (aujourd'hui il faut
  enregistrer un preset à la main, et un redémarrage remet tout sur MUTE/OFF)
- Réécriture du cœur audio en C++/JUCE si le Python montre ses limites sur
  une machine chargée
- Groupes de mute et DCA
- Verrouillage de l'interface pendant un direct, pour éviter les fausses
  manœuvres
