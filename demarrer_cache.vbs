' Lance demarrer.bat totalement en arriere-plan : aucune fenetre, aucune
' icone dans la barre des taches. Impossible a fermer par megarde pendant
' un direct (contrairement a une fenetre reduite, qui reste cliquable et
' fermable depuis la barre des taches).
'
' Le navigateur s'ouvre normalement (commande separee lancee par
' demarrer.bat) : c'est la seule interface visible, et la fermer ne
' touche pas au moteur audio qui continue de tourner cache.
'
' Pour voir la console (diagnostic) : double-cliquez demarrer.bat
' directement, ou consultez journal.log.
Set fso = CreateObject("Scripting.FileSystemObject")
chemin = fso.GetParentFolderName(WScript.ScriptFullName) & "\demarrer.bat"
Set shell = CreateObject("WScript.Shell")
shell.Run chr(34) & chemin & chr(34), 0, False
