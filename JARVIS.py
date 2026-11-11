import os
import re
import subprocess
import webbrowser
import datetime
import time
import pyttsx3
import ollama
import pyautogui
import pyperclip


# ==========================================
# VOICE ENGINE
# ==========================================

engine = pyttsx3.init()
engine.setProperty("rate", 210)


def speak(text: str) -> None:
    """Prints a response to the terminal and speaks it aloud."""
    print(f"\nJ.A.R.V.I.S.: {text}")
    engine.say(text)
    engine.runAndWait()


# ==========================================
# TOOL DEFINITIONS
# ==========================================

def open_app(app_name: str = "", **kwargs) -> str:
    """Opens specified desktop apps, websites, or web services."""
    if not app_name and kwargs:
        for val in kwargs.values():
            if val and str(val).lower() != "open_app":
                app_name = str(val)
                break

    if not app_name or str(app_name).lower() == "open_app":
        app_name = "google docs"

    name = str(app_name).lower().strip()

    if name in ["function", "", "none"]:
        return "Hello, boss! How can I help you today?"

    # Google Workspace apps
    if "doc" in name:
        if "new" in name or "create" in name:
            webbrowser.open("https://docs.new")
            return "Opened a new Google Doc."
        webbrowser.open("https://docs.google.com")
        return "Opened Google Docs."

    if "sheet" in name or "spreadsheet" in name:
        if "new" in name or "create" in name:
            webbrowser.open("https://sheets.new")
            return "Opened a new Google Sheet."
        webbrowser.open("https://sheets.google.com")
        return "Opened Google Sheets."

    if "slide" in name or "presentation" in name:
        if "new" in name or "create" in name:
            webbrowser.open("https://slides.new")
            return "Opened a new Google Slides presentation."
        webbrowser.open("https://slides.google.com")
        return "Opened Google Slides."

    # Microsoft 365 web apps
    if "word" in name:
        webbrowser.open("https://word.new")
        return "Opened Word Online."

    if "excel" in name:
        webbrowser.open("https://excel.new")
        return "Opened Excel Online."

    if "powerpoint" in name or "ppt" in name:
        webbrowser.open("https://powerpoint.new")
        return "Opened PowerPoint Online."

    # Standard browsers and media apps
    if "edge" in name:
        edge_paths = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for path in edge_paths:
            if os.path.exists(path):
                subprocess.Popen([path])
                return "Opened Microsoft Edge."
        webbrowser.open("https://www.bing.com")
        return "Opened Edge web browser."

    if "youtube" in name:
        webbrowser.open("https://youtube.com")
        return "Opened YouTube."

    if "spotify" in name:
        spotify_path = os.path.expanduser(r"~\AppData\Roaming\Spotify\Spotify.exe")
        if os.path.exists(spotify_path):
            subprocess.Popen([spotify_path])
            return "Opened Spotify desktop app."
        webbrowser.open("https://open.spotify.com")
        return "Opened Spotify web player."

    if "chrome" in name:
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome_path):
            subprocess.Popen([chrome_path])
            return "Opened Google Chrome."
        webbrowser.open("https://google.com")
        return "Opened Chrome browser."

    if "notepad" in name:
        subprocess.Popen(["notepad.exe"])
        return "Opened Notepad."

    webbrowser.open(f"https://www.bing.com/search?q={app_name}")
    return f"Opened search for {app_name}."


def close_app(app_name: str = "", **kwargs) -> str:
    """Closes a supported running program on the user's computer."""
    if not app_name and kwargs:
        app_name = next(iter(kwargs.values()), "")

    name = str(app_name).lower().strip()
    process_map = {
        "edge": "msedge.exe",
        "chrome": "chrome.exe",
        "spotify": "Spotify.exe",
        "notepad": "notepad.exe",
    }

    for key, process in process_map.items():
        if key in name:
            os.system(f"taskkill /f /im {process} >nul 2>&1")
            return f"Closed {key} successfully."

    return f"Could not determine process name for {app_name}."


def search_edge(query: str = "", **kwargs) -> str:
    """Searches the internet for a query using Microsoft Edge."""
    if not query and kwargs:
        query = next(iter(kwargs.values()), "")

    query = str(query).strip()
    from urllib.parse import quote_plus

    search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]

    for edge_path in edge_paths:
        if os.path.exists(edge_path):
            subprocess.Popen([edge_path, search_url])
            break
    else:
        webbrowser.open(search_url)

    return f"Searched Edge for '{query}'."


def calculate(expression: str = "", **kwargs) -> str:
    """Calculates a basic mathematical expression."""
    if not expression and kwargs:
        expression = next(iter(kwargs.values()), "")

    try:
        expression = str(expression)
        allowed_chars = set("0123456789+-*/(). ")
        if not expression or not all(char in allowed_chars for char in expression):
            return "I can only calculate basic mathematical expressions."

        result = eval(expression, {"__builtins__": {}}, {})
        return f"The result is {result}."
    except Exception:
        return "I couldn't calculate that expression."


def get_current_time(**kwargs) -> str:
    """Gets the current local time and date using the computer's local timezone."""
    now = datetime.datetime.now().astimezone()
    current_time = now.strftime("%I:%M %p on %A, %B %d, %Y")
    return f"The current time is {current_time}."


def take_note(note_text: str = "", **kwargs) -> str:
    """Saves a quick text note to a file on the desktop."""
    if not note_text and kwargs:
        note_text = next(iter(kwargs.values()), "")

    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    os.makedirs(desktop_path, exist_ok=True)
    file_path = os.path.join(desktop_path, "jarvis_notes.txt")

    with open(file_path, "a", encoding="utf-8") as note_file:
        timestamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        note_file.write(f"[{timestamp}] {note_text}\n")

    return "I have saved that note to your desktop."


def type_text(text: str = "", **kwargs) -> str:
    """Pastes the supplied text into the currently active application."""
    # Prefer recognised argument names rather than blindly taking the first value.
    if not isinstance(text, str) or not text.strip():
        for key in ("text", "content", "message", "value", "input", "text_to_type"):
            value = kwargs.get(key)
            if isinstance(value, str) and value.strip():
                text = value
                break

    if not isinstance(text, str) or not text.strip():
        return f"No valid text was provided. Received arguments: {kwargs}"

    try:
        # Put the exact text on the clipboard and check that it copied correctly.
        pyperclip.copy(text)
        if pyperclip.paste() != text:
            return "I couldn't verify the clipboard contents, so I didn't paste anything."

        speak("Click inside the place where you want the text. Pasting in 3 seconds.")
        time.sleep(3)
        pyautogui.hotkey("ctrl", "v", interval=0.1)

        return f"Paste command sent for {len(text)} characters."
    except Exception as error:
        return f"Typing error: {error}"


available_tools = {
    "open_app": open_app,
    "close_app": close_app,
    "search_edge": search_edge,
    "calculate": calculate,
    "get_current_time": get_current_time,
    "take_note": take_note,
    "type_text": type_text,
}


# ==========================================
# REQUEST HANDLING
# ==========================================

def process_user_request(user_input: str, history: list) -> None:
    """Processes direct commands first, then uses Ollama for other requests."""
    cleaned_input = user_input.lower().strip()

    # Catch greetings instantly.
    greetings = ["hi", "hello", "hey", "good morning", "good evening", "sup", "greetings"]
    if cleaned_input in greetings:
        reply = "Hello, boss. All systems are online and ready."
        speak(reply)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})
        return

    # Handle typing/pasting commands directly in Python. This prevents the
    # language model from accidentally sending a typing request to calculate.
    typing_command = re.match(
        r"^\s*(?:(?:j\.?a\.?r\.?v\.?i\.?s\.?)\s*[, :]\s*)?"
        r"(?:(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?(?:please\s+)?)?"
        r"(?:type|paste)\b",
        user_input,
        flags=re.IGNORECASE,
    )

    if typing_command:
        # First look for text wrapped in straight or curly quotation marks.
        quoted_match = re.search(
            r'"(.*?)"|“(.*?)”|\'(.*?)\'|‘(.*?)’',
            user_input,
            flags=re.DOTALL,
        )

        if quoted_match:
            text_to_type = next(
                (group for group in quoted_match.groups() if group is not None),
                "",
            )
        else:
            # If there are no quotes, use the words after "type" or "paste".
            text_to_type = user_input[typing_command.end():].strip()
            text_to_type = re.sub(
                r"\s+into\s+(?:(?:the|my)\s+)?"
                r"(?:document|doc|google\s+docs?|word|notepad|text\s+editor|active\s+window)"
                r"\s*[.!?]*$",
                "",
                text_to_type,
                flags=re.IGNORECASE,
            ).strip()

        if text_to_type:
            result = type_text(text=text_to_type)
        else:
            result = "What would you like me to type?"

        speak(result)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": result})
        return

    # Direct routing for common app-opening requests.
    if any(
        keyword in cleaned_input
        for keyword in ["google doc", "docs", "spreadsheet", "google sheet", "slide", "word", "excel"]
    ):
        result = open_app(app_name=cleaned_input)
        speak(result)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": result})
        return

    history.append({"role": "user", "content": user_input})

    try:
        response = ollama.chat(
            model="llama3.2:1b",
            messages=history,
            tools=list(available_tools.values()),
            keep_alive="1h",
            options={
                # A larger output allowance gives the model more room for tool arguments.
                "num_predict": 512,
                "temperature": 0.5,
            },
        )

        full_reply = ""

        if response.message.tool_calls:
            for tool_call in response.message.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments or {}

                if func_name in available_tools:
                    result_msg = available_tools[func_name](**func_args)
                    speak(result_msg)
                    full_reply += f" {result_msg}"
        elif response.message.content:
            speak(response.message.content)
            full_reply += f" {response.message.content}"

        if full_reply.strip():
            history.append({"role": "assistant", "content": full_reply.strip()})

    except Exception as error:
        speak(f"System error: {error}")


# ==========================================
# MAIN PROGRAM
# ==========================================

def main() -> None:
    speak("All systems fully operational. Ready for anything, boss.")

    history = [
        {
            "role": "system",
            "content": (
                "You are J.A.R.V.I.S., a versatile, highly intelligent local assistant. "
                "Answer general questions, calculate maths, check the time, take notes, "
                "type text into active documents using the type_text tool, or open apps via tools when requested. "
                "When asked to type or paste text, use the type_text tool if the request reaches you. "
                "Pass the complete text using the text argument and preserve the user's exact wording "
                "without paraphrasing or omitting anything. Never use calculate for typing requests. "
                "Keep answers strictly under 2 sentences unless requested otherwise. "
                "No MCU/Iron Man references. Be direct and polite."
            ),
        }
    ]

    while True:
        try:
            user_query = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            speak("Powering down systems. Goodbye, boss!")
            break

        if not user_query:
            continue

        if user_query.lower() in ["exit", "quit", "shutdown", "goodbye"]:
            speak("Powering down systems. Goodbye, boss!")
            break

        process_user_request(user_query, history)


if __name__ == "__main__":
    main()
