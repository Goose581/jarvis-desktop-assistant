# Ollama automatic startup in v1.6.4

J.A.R.V.I.S. no longer requires the Ollama tray app to have been opened manually first.

At application startup, a background worker checks the local API. If it is unavailable and `OLLAMA_HOST` is local/default, J.A.R.V.I.S. locates the installed `ollama.exe` and launches:

```cmd
ollama.exe serve
```

The process is launched without a visible console and is allowed to continue running after J.A.R.V.I.S. closes. J.A.R.V.I.S. retries the API for up to 12 seconds. It repeats this readiness check before chat and model-manager operations so it can recover if Ollama is stopped while the assistant is already open.

If `OLLAMA_HOST` points to a remote server, J.A.R.V.I.S. does not start a local Ollama process or change that setting.

## Diagnostics

- Main app log: `%LOCALAPPDATA%\JARVIS\jarvis.log`
- Ollama server log: `%LOCALAPPDATA%\JARVIS\ollama-server.log`
- Standard per-user Ollama CLI location: `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`

If the executable is not found, install Ollama for the current Windows user or open it from the Windows Start menu. No administrator permissions are required by this feature.
