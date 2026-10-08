Dim fso, dir, py
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
py = dir & "\economic_calendar.py"

CreateObject("WScript.Shell").Run "pythonw """ & py & """", 0, False
