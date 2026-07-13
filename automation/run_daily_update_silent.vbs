Set shell = CreateObject("WScript.Shell")
script = Replace(WScript.ScriptFullName, "run_daily_update_silent.vbs", "run_daily_update_hidden.ps1")
cmd = "powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & script & Chr(34)
WScript.Quit shell.Run(cmd, 0, True)