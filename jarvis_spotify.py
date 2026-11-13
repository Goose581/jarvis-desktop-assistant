"""Local Spotify desktop controls for J.A.R.V.I.S. on Windows.

Playback buttons use Windows multimedia keys, which Spotify's desktop client
normally registers globally. Spotify-only volume uses Windows Core Audio's
per-application audio session through Pycaw; it does not change system volume.
This does not require Spotify API credentials. Windows may route playback keys
to another active media session, but volume changes target Spotify.exe only.
"""
from __future__ import annotations

import ctypes
import math
import os
import re
import subprocess
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any


_MEDIA_KEYS = {
    "play_pause": 0xB3,  # VK_MEDIA_PLAY_PAUSE
    "next": 0xB0,        # VK_MEDIA_NEXT_TRACK
    "previous": 0xB1,    # VK_MEDIA_PREV_TRACK
}
_MAX_SEARCH_LENGTH = 300
DEFAULT_VOLUME_STEP = 5


def _spotify_candidates() -> list[Path]:
    candidates: list[Path] = []
    appdata = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Spotify" / "Spotify.exe")
    if local:
        candidates.extend([
            Path(local) / "Programs" / "Spotify" / "Spotify.exe",
            Path(local) / "Spotify" / "Spotify.exe",
        ])
    candidates.append(Path.home() / "AppData" / "Roaming" / "Spotify" / "Spotify.exe")
    # Preserve order while avoiding duplicate paths.
    return list(dict.fromkeys(candidates))


def find_spotify_executable() -> Path | None:
    """Find the classic per-user Spotify desktop executable, if installed."""
    for candidate in _spotify_candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def spotify_is_running() -> bool:
    """Check for Spotify.exe without raising when tasklist is unavailable."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return bool(re.search(r'"Spotify\.exe"', result.stdout or "", flags=re.IGNORECASE))
    except (OSError, subprocess.SubprocessError):
        return False


def _open_uri(uri: str, web_fallback: str) -> bool:
    """Open a Spotify URI through Windows' registered protocol handler."""
    if os.name == "nt" and hasattr(os, "startfile"):
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
            return True
        except OSError:
            pass
    try:
        return webbrowser.open(web_fallback) is not False
    except Exception:
        return False


def open_spotify() -> str:
    """Launch Spotify desktop, with the official web player as fallback."""
    executable = find_spotify_executable()
    if executable is not None:
        try:
            subprocess.Popen(
                [str(executable)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return "Opened Spotify."
        except OSError:
            pass
    if _open_uri("spotify:", "https://open.spotify.com/"):
        return "Opened Spotify."
    return "I couldn't open Spotify. Check that the Spotify app is installed or that you can access open.spotify.com."


def search_spotify(query: str) -> str:
    """Open a search in Spotify; the user chooses the matching result to play."""
    if not isinstance(query, str):
        return "Tell me what you'd like to search for on Spotify."
    phrase = query.strip()
    if not phrase:
        return "What would you like me to search for on Spotify?"
    if len(phrase) > _MAX_SEARCH_LENGTH:
        return f"Spotify searches must be {_MAX_SEARCH_LENGTH} characters or fewer."
    encoded = urllib.parse.quote(phrase, safe="")
    uri = f"spotify:search:{encoded}"
    web_url = "https://open.spotify.com/search/" + encoded
    if not _open_uri(uri, web_url):
        return "I couldn't open Spotify search. Check that Spotify or a browser is available."
    return f"Opened Spotify search for '{phrase}'. Choose the track, artist or playlist you want to play."


def _send_media_key(action: str) -> None:
    """Send a Windows multimedia key without stealing keyboard focus."""
    if action not in _MEDIA_KEYS:
        raise ValueError("Unsupported Spotify playback action.")
    if os.name != "nt":
        raise OSError("Spotify desktop media-key controls are currently supported on Windows.")
    user32 = ctypes.windll.user32
    vk = _MEDIA_KEYS[action]
    keyeventf_extendedkey = 0x0001
    keyeventf_keyup = 0x0002
    user32.keybd_event(vk, 0, keyeventf_extendedkey, 0)
    user32.keybd_event(vk, 0, keyeventf_extendedkey | keyeventf_keyup, 0)



def _run_on_spotify_audio_sessions(operation):
    """Run an operation on Spotify's own Windows audio sessions.

    Uses Pycaw's per-session SimpleAudioVolume interface. It deliberately does
    not touch the audio endpoint, so Windows master volume and other apps are
    left unchanged.
    """
    if os.name != "nt":
        raise OSError("Spotify-only volume control is available on Windows.")

    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
    except ImportError as error:
        raise RuntimeError(
            "Spotify-only volume control is unavailable because the Windows audio component is missing. "
            "Rebuild J.A.R.V.I.S. with the included pycaw dependency."
        ) from error

    initialized = False
    sessions = []
    spotify_sessions = []
    session = None
    process = None
    try:
        # Core Audio is COM-based. Initialize COM in the thread performing the
        # operation and balance it even when enumeration or volume changes fail.
        comtypes.CoInitialize()
        initialized = True
        all_sessions = getattr(AudioUtilities, "GetSessionsFromAllDevices", None)
        sessions = all_sessions() if callable(all_sessions) else AudioUtilities.GetAllSessions()
        for session in sessions:
            try:
                process = session.Process
                if process is not None and str(process.name()).casefold() == "spotify.exe":
                    spotify_sessions.append(session)
            except Exception:
                # A process can exit while Windows' audio-session list is read.
                continue
        if not spotify_sessions:
            return None
        return operation(spotify_sessions)
    finally:
        # Release session references while the COM apartment is still active.
        session = None
        process = None
        # Drop this helper's references without mutating any object returned by
        # the callback (the production callbacks return only scalar state).
        sessions = None
        spotify_sessions = None
        if initialized:
            comtypes.CoUninitialize()


def _valid_volume_percent(value: Any) -> float:
    """Parse a finite numeric volume and clamp it to Windows' 0..100 range."""
    if isinstance(value, bool):
        raise ValueError("Volume must be a number from 0 to 100.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Volume must be a number from 0 to 100.") from error
    if not math.isfinite(number):
        raise ValueError("Volume must be a finite number from 0 to 100.")
    return min(100.0, max(0.0, number))


def get_spotify_audio_state() -> dict[str, Any] | None:
    """Return Spotify's current app-session volume/mute state, or None."""
    def read(sessions):
        volumes: list[float] = []
        muted_values: list[bool] = []
        for session in sessions:
            audio = session.SimpleAudioVolume
            volumes.append(float(audio.GetMasterVolume()) * 100.0)
            muted_values.append(bool(audio.GetMute()))
        if not volumes:
            return None
        return {
            "volume": int(round(sum(volumes) / len(volumes))),
            "muted": any(muted_values),
            "sessions": len(volumes),
        }

    return _run_on_spotify_audio_sessions(read)


def get_spotify_volume_percent() -> int | None:
    """Return Spotify's own volume percentage, without reading master volume."""
    state = get_spotify_audio_state()
    return int(state["volume"]) if state else None


def set_spotify_volume_percent(value: Any) -> int | None:
    """Set every Spotify audio session to a percentage, leaving other apps alone."""
    target = _valid_volume_percent(value)

    def write(sessions):
        scalar = target / 100.0
        for session in sessions:
            session.SimpleAudioVolume.SetMasterVolume(scalar, None)
        return int(round(target))

    return _run_on_spotify_audio_sessions(write)


def adjust_spotify_volume_percent(delta: Any = DEFAULT_VOLUME_STEP) -> int | None:
    """Raise/lower Spotify volume by a percentage amount, clamped to 0..100."""
    if isinstance(delta, bool):
        raise ValueError("Volume adjustment must be a number.")
    try:
        change = float(delta)
    except (TypeError, ValueError) as error:
        raise ValueError("Volume adjustment must be a number.") from error
    if not math.isfinite(change):
        raise ValueError("Volume adjustment must be finite.")

    def adjust(sessions):
        current_values = [float(session.SimpleAudioVolume.GetMasterVolume()) * 100.0 for session in sessions]
        current = sum(current_values) / len(current_values)
        target = min(100.0, max(0.0, current + change))
        scalar = target / 100.0
        for session in sessions:
            session.SimpleAudioVolume.SetMasterVolume(scalar, None)
        return int(round(target))

    return _run_on_spotify_audio_sessions(adjust)


def set_spotify_muted(muted: bool) -> bool | None:
    """Mute/unmute Spotify's own audio sessions, not the Windows output device."""
    if not isinstance(muted, bool):
        raise ValueError("Mute state must be true or false.")

    def change(sessions):
        for session in sessions:
            session.SimpleAudioVolume.SetMute(1 if muted else 0, None)
        return muted

    return _run_on_spotify_audio_sessions(change)

def spotify_control(action: str = "open", query: str = "", level: Any = None, **kwargs: Any) -> str:
    """Open/search/control Spotify, including Spotify-only session volume.

    Volume controls use Windows Core Audio's per-process session interface;
    they do not change the computer's master volume or other applications.
    """
    if not isinstance(action, str):
        return "Choose an action: open, play_pause, next, previous, search, volume_up, volume_down, set_volume, get_volume, mute or unmute."
    selected = action.strip().casefold().replace("-", "_").replace(" ", "_")
    if not query:
        for key in ("query", "search", "track", "artist", "name", "text"):
            value = kwargs.get(key)
            if isinstance(value, str) and value.strip():
                query = value
                break
    if level is None:
        for key in ("level", "volume", "percent", "value"):
            if key in kwargs:
                level = kwargs[key]
                break

    if selected == "open":
        return open_spotify()
    if selected == "search":
        return search_spotify(query)

    if selected in {"get_volume", "volume_status", "check_volume"}:
        try:
            state = get_spotify_audio_state()
            if state is None:
                return "Spotify doesn't have an active audio session yet. Start playing something in Spotify, then check its volume again."
            muted_text = "muted" if state["muted"] else "unmuted"
            return f"Spotify's own volume is {state['volume']}% ({muted_text}). Your Windows master volume and other apps are unchanged."
        except Exception as error:
            return f"I couldn't read Spotify's app volume: {error}"

    if selected in {"set_volume", "volume_set", "set_spotify_volume"}:
        if level is None:
            return "Tell me the Spotify volume percentage to set, from 0 to 100."
        try:
            result = set_spotify_volume_percent(level)
            if result is None:
                return "Spotify doesn't have an active audio session yet. Start playing something in Spotify, then set its volume."
            return f"Set Spotify's own volume to {result}%. Windows master volume and other apps were not changed."
        except Exception as error:
            return f"I couldn't change Spotify's app volume: {error}"

    if selected in {"volume_up", "louder", "increase_volume", "spotify_volume_up"}:
        delta = DEFAULT_VOLUME_STEP if level is None else level
        try:
            result = adjust_spotify_volume_percent(abs(float(delta)))
            if result is None:
                return "Spotify doesn't have an active audio session yet. Start playing something in Spotify, then adjust its volume."
            return f"Raised Spotify's own volume to {result}%. Windows master volume and other apps were not changed."
        except Exception as error:
            return f"I couldn't raise Spotify's app volume: {error}"

    if selected in {"volume_down", "quieter", "decrease_volume", "spotify_volume_down"}:
        delta = DEFAULT_VOLUME_STEP if level is None else level
        try:
            result = adjust_spotify_volume_percent(-abs(float(delta)))
            if result is None:
                return "Spotify doesn't have an active audio session yet. Start playing something in Spotify, then adjust its volume."
            return f"Lowered Spotify's own volume to {result}%. Windows master volume and other apps were not changed."
        except Exception as error:
            return f"I couldn't lower Spotify's app volume: {error}"

    if selected in {"mute", "mute_spotify"}:
        try:
            result = set_spotify_muted(True)
            if result is None:
                return "Spotify doesn't have an active audio session yet. Start playing something in Spotify, then mute it."
            return "Muted Spotify only. Your Windows master volume and other apps are unchanged."
        except Exception as error:
            return f"I couldn't mute Spotify: {error}"

    if selected in {"unmute", "unmute_spotify"}:
        try:
            result = set_spotify_muted(False)
            if result is None:
                return "Spotify doesn't have an active audio session yet. Start playing something in Spotify, then unmute it."
            return "Unmuted Spotify only. Your Windows master volume and other apps are unchanged."
        except Exception as error:
            return f"I couldn't unmute Spotify: {error}"

    if selected in {"pause", "resume", "play", "toggle", "playpause", "play_pause"}:
        selected = "play_pause"
    elif selected in {"skip", "skip_track", "next_track", "next_song"}:
        selected = "next"
    elif selected in {"back", "previous_track", "previous_song", "prev"}:
        selected = "previous"

    if selected not in _MEDIA_KEYS:
        return "Spotify action not recognised. Try open, play_pause, next, previous, search, volume_up, volume_down, set_volume, get_volume, mute or unmute."

    if not spotify_is_running():
        opened = open_spotify()
        return f"{opened} Spotify wasn't running, so I haven't sent a playback key yet. Start Spotify playback, then ask me again."
    try:
        _send_media_key(selected)
    except (OSError, ValueError) as error:
        return f"I couldn't control Spotify: {error}"
    labels = {
        "play_pause": "Sent the play/pause command to the active media session.",
        "next": "Skipped to the next track in the active media session.",
        "previous": "Skipped to the previous track in the active media session.",
    }
    return labels[selected] + " If another media app is active, Windows may send the command to that app instead."


def handle_spotify_command(user_input: str) -> str | None:
    """Recognise explicit Spotify commands for fast local execution."""
    text = str(user_input).strip()
    if not text:
        return None
    text = re.sub(r"^(?:j\.?a\.?r\.?v\.?i\.?s\.?)[, :]\s*", "", text, flags=re.IGNORECASE)
    patterns = [
        (r"^(?:please\s+)?(?:search|find)\s+(?:spotify\s+for|on\s+spotify\s+for)\s+(.+?)\s*[.!?]*$", "search"),
        (r"^(?:please\s+)?(?:play|find)\s+(.+?)\s+on\s+spotify\s*[.!?]*$", "search"),
        (r"^(?:please\s+)?(?:search|find)\s+spotify\s+(.+?)\s*[.!?]*$", "search"),
    ]
    for pattern, action in patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            return spotify_control(action, match.group(1).strip())

    volume_patterns = (
        (r"^(?:please\s+)?(?:set|change)\s+(?:the\s+)?(?:spotify(?:'s)?\s+volume|volume\s+of\s+spotify)\s+to\s+(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)?\s*[.!?]*$", "set_volume"),
        (r"^(?:please\s+)?(?:set|change)\s+spotify\s+to\s+(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)?\s+volume\s*[.!?]*$", "set_volume"),
        (r"^(?:please\s+)?(?:turn|turn the)\s+(?:volume\s+of\s+spotify|spotify(?:'s)?\s+volume|spotify\s+volume|spotify)\s+(up|down)\s*[.!?]*$", "direction"),
        (r"^(?:please\s+)?turn\s+(up|down)\s+(?:the\s+)?(?:volume\s+of\s+spotify|spotify(?:'s)?\s+volume|spotify\s+volume)\s*[.!?]*$", "direction"),
        (r"^(?:please\s+)?(?:increase|raise|boost)\s+(?:the\s+)?(?:volume\s+of\s+spotify|spotify(?:'s)?\s+volume|spotify\s+volume)(?:\s+by\s+(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)?)?\s*[.!?]*$", "up"),
        (r"^(?:please\s+)?(?:decrease|lower|reduce)\s+(?:the\s+)?(?:volume\s+of\s+spotify|spotify(?:'s)?\s+volume|spotify\s+volume)(?:\s+by\s+(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)?)?\s*[.!?]*$", "down"),
        (r"^(?:what(?:'s| is)|check|get)\s+(?:the\s+)?(?:spotify(?:'s)?\s+volume|volume\s+of\s+spotify)\s*[?!.]*$", "get_volume"),
        (r"^(?:please\s+)?mute\s+(?:my\s+)?spotify\s*[.!?]*$", "mute"),
        (r"^(?:please\s+)?unmute\s+(?:my\s+)?spotify\s*[.!?]*$", "unmute"),
        (r"^spotify\s+volume\s+(up|down)\s*[.!?]*$", "direction"),
        (r"^spotify\s+volume\s+(?:to\s+)?(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)?\s*[.!?]*$", "set_volume"),
    )
    for pattern, action in volume_patterns:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if action == "direction":
            return spotify_control("volume_up" if match.group(1).casefold() == "up" else "volume_down")
        if action == "up":
            amount = match.group(1)
            return spotify_control("volume_up", level=amount if amount else None)
        if action == "down":
            amount = match.group(1)
            return spotify_control("volume_down", level=amount if amount else None)
        if action == "set_volume":
            return spotify_control("set_volume", level=match.group(1))
        return spotify_control(action)

    controls = (
        (r"^(?:please\s+)?(?:pause|resume|play|toggle)\s+(?:my\s+)?spotify(?:\s+(?:music|playback))?\s*[.!?]*$", "play_pause"),
        (r"^(?:please\s+)?(?:skip|next)(?:\s+(?:the\s+)?(?:song|track))?\s+(?:on\s+)?spotify\s*[.!?]*$", "next"),
        (r"^(?:please\s+)?(?:previous|prev|back)(?:\s+(?:the\s+)?(?:song|track))?\s+(?:on\s+)?spotify\s*[.!?]*$", "previous"),
        (r"^spotify\s+(?:pause|resume|play|toggle)\s*[.!?]*$", "play_pause"),
        (r"^spotify\s+(?:skip|next)(?:\s+(?:song|track))?\s*[.!?]*$", "next"),
        (r"^spotify\s+(?:previous|prev|back)(?:\s+(?:song|track))?\s*[.!?]*$", "previous"),
    )
    for pattern, action in controls:
        if re.match(pattern, text, flags=re.IGNORECASE):
            return spotify_control(action)
    if re.fullmatch(r"(?:please\s+)?open\s+(?:the\s+)?spotify\s*[.!?]*", text, flags=re.IGNORECASE):
        return open_spotify()
    return None
