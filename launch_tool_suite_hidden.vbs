Option Explicit
' Hidden wrapper for launch_tool_suite.ps1.

Dim shell, args, scriptPath, command, i, value
Set shell = CreateObject("WScript.Shell")
Set args = WScript.Arguments

If args.Count = 0 Then
  WScript.Quit 1
End If

scriptPath = args(0)
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Quote(scriptPath)

For i = 1 To args.Count - 1
  value = args(i)
  command = command & " " & Quote(value)
Next

shell.Run command, 0, False

Function Quote(ByVal text)
  Quote = Chr(34) & Replace(text, Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
