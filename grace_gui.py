import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
import requests

LOGIN_URL = "https://api.aryankaushik.space/api/auth/login"
GRACE_URL = "https://api.aryankaushik.space/api/ai/grace/respond"
TITLE_URL = "https://api.aryankaushik.space/api/ai/grace/generate-title"

# Golden-green / dark theme
BG = "#0a0f0b"
SIDEBAR = "#0d1510"
HEADER = "#0d1410"
COMPOSER = "#121a14"
COMPOSER_FOCUS = "#162219"
PANEL = "#111911"
PANEL_2 = "#172117"
GOLD_GREEN = "#b6c86a"
GOLD_GREEN_BRIGHT = "#d1e68a"
GOLD_GREEN_DARK = "#6f823e"
TEXT = "#eef3e6"
TEXT_MUTED = "#8d9b8b"
TEXT_DIM = "#5f6b61"
USER_BUBBLE = "#26361f"
ASSISTANT_BUBBLE = "#141c16"
BORDER = "#1f2a21"
ERROR = "#f28b82"


def make_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_json(response: requests.Response):
    try:
        return response.json()
    except ValueError:
        return None


class LoginWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Aero • Grace")
        self.root.geometry("460x600")
        self.root.minsize(420, 520)
        self.root.configure(bg=BG)
        self.token = None
        self.username = None
        self.build()

    def build(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)

        card = tk.Frame(
            outer,
            bg=SIDEBAR,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.place(relx=0.5, rely=0.5, anchor="center", width=390, height=455)

        tk.Label(card, text="AERO", bg=SIDEBAR, fg=TEXT,
                 font=("Segoe UI", 30, "bold")).pack(pady=(42, 0))
        tk.Label(card, text="GRACE", bg=SIDEBAR, fg=GOLD_GREEN_BRIGHT,
                 font=("Segoe UI", 13, "bold")).pack(pady=(0, 2))
        tk.Label(card, text="@yorichiiprime", bg=SIDEBAR, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(pady=(0, 34))

        tk.Label(card, text="Email / Username", bg=SIDEBAR, fg=TEXT_MUTED,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=32)
        self.identifier = tk.Entry(
            card, bg=COMPOSER, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Segoe UI", 11)
        )
        self.identifier.pack(fill="x", padx=32, ipady=9, pady=(6, 18))

        tk.Label(card, text="Password", bg=SIDEBAR, fg=TEXT_MUTED,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=32)
        self.password = tk.Entry(
            card, show="•", bg=COMPOSER, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Segoe UI", 11)
        )
        self.password.pack(fill="x", padx=32, ipady=9, pady=(6, 22))

        self.login_button = tk.Button(
            card, text="LOGIN", command=self.login,
            bg=GOLD_GREEN, fg="#10140d",
            activebackground=GOLD_GREEN_BRIGHT, activeforeground="#10140d",
            relief="flat", borderwidth=0,
            font=("Segoe UI", 10, "bold"), cursor="hand2"
        )
        self.login_button.pack(fill="x", padx=32, ipady=10)

        self.status = tk.Label(
            card, text="", bg=SIDEBAR, fg=TEXT_MUTED,
            font=("Segoe UI", 9), wraplength=315
        )
        self.status.pack(pady=14)

        self.password.bind("<Return>", lambda _event: self.login())
        self.identifier.focus_set()

    def login(self):
        identifier = self.identifier.get().strip()
        password = self.password.get()
        if not identifier or not password:
            self.set_status("Enter your email/username and password.", ERROR)
            return

        self.login_button.config(state="disabled", text="LOGGING IN...")
        self.set_status("Connecting to Aero…", TEXT_MUTED)
        threading.Thread(
            target=self.login_worker, args=(identifier, password), daemon=True
        ).start()

    def login_worker(self, identifier, password):
        try:
            response = requests.post(
                LOGIN_URL,
                json={"identifier": identifier, "password": password},
                timeout=20,
            )
            data = safe_json(response)
            if not isinstance(data, dict):
                raise ValueError("Invalid JSON response from Aero.")

            message = data.get("message")
            if message == "Invalid credentials":
                self.root.after(0, lambda: self.login_failed(
                    "Invalid email/username or password."
                ))
                return

            if message == "OTP sent to registered email":
                self.root.after(0, lambda: self.login_failed(
                    "OTP is required for this account. This client does not implement the OTP screen yet."
                ))
                return

            token = data.get("accessToken")
            if not token:
                self.root.after(0, lambda: self.login_failed(
                    "Login response did not contain an access token."
                ))
                return

            self.token = token
            self.username = str(data.get("username") or identifier)
            self.root.after(0, self.open_chat)

        except requests.RequestException as exc:
            self.root.after(0, lambda: self.login_failed(f"Network error: {exc}"))
        except ValueError as exc:
            self.root.after(0, lambda: self.login_failed(str(exc)))

    def set_status(self, text, color):
        self.status.config(text=text, fg=color)

    def login_failed(self, text):
        self.login_button.config(state="normal", text="LOGIN")
        self.set_status(text, ERROR)

    def open_chat(self):
        self.root.destroy()
        chat_root = tk.Tk()
        GraceApp(chat_root, self.token, self.username)
        chat_root.mainloop()


class MessageBubble:
    def __init__(self, parent, role, text):
        self.role = role
        self.text = text
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=24, pady=(4, 8))
        self.row = row

        if role == "user":
            outer = tk.Frame(
                row, bg=USER_BUBBLE,
                highlightbackground="#35462b", highlightthickness=1
            )
            outer.pack(anchor="e", padx=(90, 0))
            tk.Label(
                outer, text="You", bg=USER_BUBBLE, fg=GOLD_GREEN_BRIGHT,
                font=("Segoe UI", 8, "bold")
            ).pack(anchor="w", padx=14, pady=(9, 2))
            self.label = tk.Label(
                outer, text=text, bg=USER_BUBBLE, fg=TEXT,
                justify="left", anchor="w", wraplength=800,
                font=("Segoe UI", 10)
            )
            self.label.pack(fill="x", padx=14, pady=(0, 11))
        else:
            outer = tk.Frame(row, bg=BG)
            outer.pack(anchor="w", fill="x", padx=(0, 65))
            tk.Label(
                outer, text="GRACE", bg=BG, fg=GOLD_GREEN_BRIGHT,
                font=("Segoe UI", 8, "bold")
            ).pack(anchor="w")
            self.label = tk.Label(
                outer, text=text, bg=ASSISTANT_BUBBLE, fg=TEXT,
                justify="left", anchor="w", wraplength=880,
                font=("Segoe UI", 10), padx=16, pady=13,
                highlightbackground=BORDER, highlightthickness=1
            )
            self.label.pack(anchor="w", fill="x", pady=(6, 0))

    def set_text(self, text):
        self.text = text
        self.label.config(text=text)

    def append(self, chunk):
        self.text += chunk
        self.label.config(text=self.text)


class GraceApp:
    def __init__(self, root, token, username):
        self.root = root
        self.token = token
        self.username = username
        self.root.title("Aero • Grace")
        self.root.geometry("1250x800")
        self.root.minsize(900, 600)
        self.root.configure(bg=BG)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        })

        # Exactly one chat per desktop session. No duplicate-chat button.
        self.conversation_id = make_id("gc")
        self.history = []
        self.busy = False
        self.selected_files = []
        self.current_assistant_bubble = None
        self.ui_queue = queue.Queue()

        self.build_ui()
        self.show_welcome()
        self.process_ui_queue()
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        try:
            self.session.close()
        finally:
            self.root.destroy()

    def toggle_fullscreen(self, _event=None):
        current = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not current)

    def exit_fullscreen(self, _event=None):
        if bool(self.root.attributes("-fullscreen")):
            self.root.attributes("-fullscreen", False)

    def build_ui(self):
        sidebar = tk.Frame(
            self.root, bg=SIDEBAR, width=245,
            highlightbackground=BORDER, highlightthickness=1
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="@yorichiiprime", bg=SIDEBAR, fg=GOLD_GREEN_BRIGHT,
            font=("Segoe UI", 14, "bold")
        ).pack(anchor="w", padx=20, pady=(24, 2))
        tk.Label(
            sidebar, text="Aero • Grace", bg=SIDEBAR, fg=TEXT_MUTED,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=20)

        profile = tk.Frame(
            sidebar, bg=PANEL, highlightbackground=BORDER, highlightthickness=1
        )
        profile.pack(fill="x", padx=14, pady=24)
        tk.Label(
            profile, text="G", bg=GOLD_GREEN, fg="#11150d", width=3, height=2,
            font=("Segoe UI", 15, "bold")
        ).pack(side="left", padx=12, pady=12)

        info = tk.Frame(profile, bg=PANEL)
        info.pack(side="left", fill="x", expand=True, pady=12)
        tk.Label(info, text="Grace", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(info, text="AI assistant", bg=PANEL, fg=TEXT_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(1, 0))

        tk.Label(
            sidebar, text="CURRENT CHAT", bg=SIDEBAR, fg=TEXT_DIM,
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w", padx=20, pady=(2, 7))

        current = tk.Frame(
            sidebar, bg=PANEL_2,
            highlightbackground=GOLD_GREEN_DARK, highlightthickness=1
        )
        current.pack(fill="x", padx=14)
        tk.Label(current, text="●", bg=PANEL_2, fg=GOLD_GREEN,
                 font=("Segoe UI", 12)).pack(side="left", padx=(12, 8), pady=10)
        self.sidebar_title = tk.Label(
            current, text="New conversation", bg=PANEL_2, fg=TEXT,
            font=("Segoe UI", 9), anchor="w"
        )
        self.sidebar_title.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)

        tk.Label(
            sidebar,
            text="One conversation per client session.\nNo duplicate chats are created.",
            bg=SIDEBAR, fg=TEXT_DIM, justify="left", font=("Segoe UI", 8)
        ).pack(anchor="w", padx=20, pady=14)

        user_box = tk.Frame(sidebar, bg=SIDEBAR)
        user_box.pack(side="bottom", fill="x", padx=14, pady=15)
        tk.Label(user_box, text=f"@{self.username}", bg=SIDEBAR, fg=TEXT_MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(user_box, text="Authenticated with Aero", bg=SIDEBAR, fg=TEXT_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))

        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self.build_header()
        self.build_chat_area()
        self.build_composer()

    def build_header(self):
        header = tk.Frame(
            self.main, bg=HEADER, height=64,
            highlightbackground=BORDER, highlightthickness=1
        )
        header.pack(fill="x")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=HEADER)
        left.pack(side="left", padx=24)
        self.header_title = tk.Label(
            left, text="New conversation", bg=HEADER, fg=TEXT,
            font=("Segoe UI", 13, "bold")
        )
        self.header_title.pack(anchor="w", pady=(12, 0))
        tk.Label(
            left, text="Grace • online", bg=HEADER, fg=GOLD_GREEN,
            font=("Segoe UI", 8)
        ).pack(anchor="w")

        self.credits = tk.Label(
            header, text="", bg=HEADER, fg=TEXT_MUTED, font=("Segoe UI", 8)
        )
        self.credits.pack(side="right", padx=24)

    def build_chat_area(self):
        area = tk.Frame(self.main, bg=BG)
        area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(area, bg=BG, highlightthickness=0, borderwidth=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(
            area, orient="vertical", command=self.canvas.yview,
            troughcolor=BG, bg=PANEL, activebackground=GOLD_GREEN_DARK, relief="flat"
        )
        scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.chat_frame = tk.Frame(self.canvas, bg=BG)
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.chat_frame, anchor="nw"
        )
        self.chat_frame.bind("<Configure>", self.on_chat_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

    def on_chat_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.canvas.after_idle(self.scroll_to_bottom)

    def on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def scroll_to_bottom(self):
        self.canvas.yview_moveto(1.0)

    def show_welcome(self):
        wrapper = tk.Frame(self.chat_frame, bg=BG)
        wrapper.pack(fill="x", pady=(95, 35))
        tk.Label(wrapper, text="Grace", bg=BG, fg=GOLD_GREEN_BRIGHT,
                 font=("Segoe UI", 28, "bold")).pack()
        tk.Label(wrapper, text="How can I help you today?", bg=BG, fg=TEXT_MUTED,
                 font=("Segoe UI", 12)).pack(pady=(8, 0))
        tk.Label(
            wrapper,
            text="Ask a question, work through code, or continue your Aero workspace.",
            bg=BG, fg=TEXT_DIM, font=("Segoe UI", 9)
        ).pack(pady=(5, 0))

    def clear_welcome(self):
        for child in list(self.chat_frame.winfo_children()):
            child.destroy()

    def build_composer(self):
        outer = tk.Frame(self.main, bg=BG)
        outer.pack(fill="x", padx=28, pady=(8, 20))

        self.attachment_bar = tk.Frame(outer, bg=BG)
        self.attachment_bar.pack(fill="x")

        composer = tk.Frame(
            outer, bg=COMPOSER,
            highlightbackground=BORDER, highlightthickness=1
        )
        composer.pack(fill="x")

        controls = tk.Frame(composer, bg=COMPOSER)
        controls.pack(side="left", fill="y")

        self.attach_button = tk.Button(
            controls, text="＋", bg=COMPOSER, fg=GOLD_GREEN,
            activebackground=COMPOSER_FOCUS, activeforeground=GOLD_GREEN_BRIGHT,
            relief="flat", borderwidth=0, font=("Segoe UI", 18), cursor="hand2",
            command=self.pick_files
        )
        self.attach_button.pack(side="left", padx=(8, 3), pady=8)

        self.input_box = tk.Text(
            composer, bg=COMPOSER, fg=TEXT, insertbackground=TEXT,
            selectbackground=GOLD_GREEN_DARK, selectforeground=TEXT,
            relief="flat", borderwidth=0, highlightthickness=0,
            wrap="word", height=3, font=("Segoe UI", 11)
        )
        self.input_box.pack(side="left", fill="both", expand=True, padx=(2, 4), pady=7)

        self.send_button = tk.Button(
            controls, text="➤", bg=COMPOSER, fg=GOLD_GREEN_BRIGHT,
            activebackground=COMPOSER_FOCUS, activeforeground=GOLD_GREEN_BRIGHT,
            relief="flat", borderwidth=0, font=("Segoe UI", 20, "bold"),
            cursor="hand2", command=self.send_message
        )
        self.send_button.pack(side="left", padx=(2, 10), pady=6)

        tk.Label(
            outer,
            text="Enter to send • Shift+Enter for a new line • F11 fullscreen",
            bg=BG, fg=TEXT_DIM, font=("Segoe UI", 8)
        ).pack(anchor="e", pady=(5, 0))
        self.input_box.bind("<Return>", self.handle_enter)

    def handle_enter(self, event):
        if event.state & 0x1:
            return None
        self.send_message()
        return "break"

    def pick_files(self):
        files = filedialog.askopenfilenames(
            title="Attach files",
            filetypes=[
                ("Common files", "*.txt *.md *.json *.csv *.py *.js *.ts *.html *.css *.xml *.yaml *.yml *.png *.jpg *.jpeg *.gif *.webp *.pdf"),
                ("All files", "*.*"),
            ],
        )
        if not files:
            return
        for path in files:
            if path not in self.selected_files:
                self.selected_files.append(path)
        self.render_attachment_bar()

    def remove_file(self, path):
        self.selected_files = [x for x in self.selected_files if x != path]
        self.render_attachment_bar()

    def render_attachment_bar(self):
        for child in self.attachment_bar.winfo_children():
            child.destroy()
        for path in self.selected_files:
            chip = tk.Frame(
                self.attachment_bar, bg=PANEL,
                highlightbackground=BORDER, highlightthickness=1
            )
            chip.pack(side="left", padx=(0, 6), pady=(0, 6))
            tk.Label(
                chip, text=Path(path).name, bg=PANEL, fg=TEXT_MUTED,
                font=("Segoe UI", 8)
            ).pack(side="left", padx=(8, 4), pady=5)
            tk.Button(
                chip, text="×", bg=PANEL, fg=GOLD_GREEN,
                activebackground=PANEL, activeforeground=GOLD_GREEN_BRIGHT,
                relief="flat", borderwidth=0,
                command=lambda p=path: self.remove_file(p)
            ).pack(side="left", padx=(0, 5))

    def send_message(self):
        if self.busy:
            return
        text = self.input_box.get("1.0", "end-1c").strip()
        if not text and not self.selected_files:
            return

        # The supplied /respond contract has no attachment parameter.
        # Do not invent one or silently upload files to an unknown route.
        if self.selected_files:
            messagebox.showinfo(
                "Grace attachments",
                "The file picker is enabled, but the real Grace upload API contract was not provided.\n\n"
                "Selected files are kept in the composer; no unsupported upload request is sent."
            )
            return

        self.clear_welcome()
        client_message_id = make_id("m")
        self.history.append({
            "id": client_message_id,
            "role": "user",
            "content": text,
            "at": utc_now(),
        })
        self.add_message_bubble("user", text)
        self.input_box.delete("1.0", "end")
        self.busy = True
        self.set_composer_state(False)

        threading.Thread(
            target=self.grace_worker,
            args=(self.conversation_id, text, client_message_id),
            daemon=True,
        ).start()

        user_messages = sum(1 for item in self.history if item["role"] == "user")
        if user_messages == 1:
            threading.Thread(target=self.generate_title, args=(text,), daemon=True).start()

    def set_composer_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self.input_box.config(state=state)
        self.send_button.config(state=state)
        self.attach_button.config(state=state)

    def add_message_bubble(self, role, text):
        bubble = MessageBubble(self.chat_frame, role, text)
        self.chat_frame.update_idletasks()
        self.scroll_to_bottom()
        return bubble

    def grace_worker(self, conversation_id, message, client_message_id):
        # This matches the observed Grace request shape.
        payload = {
            "message": message,
            "conversationHistory": self.history,
            "mode": "normal",
            "effort": "instant",
            "conversationId": conversation_id,
            "clientMessageId": client_message_id,
            "capabilities": ["workspace_v2", "ask_user", "drawings_v1"],
        }
        try:
            with self.session.post(
                GRACE_URL, json=payload, stream=True, timeout=180
            ) as response:
                if response.status_code != 200:
                    body = response.text[:1200]
                    self.ui_queue.put((
                        "error",
                        f"Grace returned HTTP {response.status_code}\n{body}"
                    ))
                    return

                full_answer = ""
                self.ui_queue.put(("assistant_start",))

                for line in response.iter_lines(decode_unicode=True):
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type")
                    if event_type == "chunk":
                        chunk = event.get("content", "")
                        if chunk:
                            full_answer += chunk
                            self.ui_queue.put(("chunk", chunk))
                    elif event_type == "done":
                        server_full = event.get("fullContent")
                        if isinstance(server_full, str):
                            full_answer = server_full
                        self.ui_queue.put(("credits", event.get("remainingCredits")))

                self.ui_queue.put(("assistant_done", full_answer))

        except requests.Timeout:
            self.ui_queue.put(("error", "Grace request timed out."))
        except requests.RequestException as exc:
            self.ui_queue.put(("error", f"Connection error: {exc}"))

    def generate_title(self, message):
        try:
            response = self.session.post(
                TITLE_URL, json={"message": message}, timeout=20
            )
            if response.status_code != 200:
                return
            data = safe_json(response)
            if not isinstance(data, dict):
                return
            title = data.get("title")
            if not isinstance(title, str):
                return
            title = title.strip()
            if not title or title.lower() == "new":
                return
            self.ui_queue.put(("title", title))
        except requests.RequestException:
            pass

    def process_ui_queue(self):
        try:
            while True:
                item = self.ui_queue.get_nowait()
                event = item[0]
                if event == "assistant_start":
                    self.current_assistant_bubble = self.add_message_bubble("assistant", "")
                elif event == "chunk":
                    chunk = item[1]
                    if self.current_assistant_bubble:
                        self.current_assistant_bubble.append(chunk)
                        self.chat_frame.update_idletasks()
                        self.scroll_to_bottom()
                elif event == "assistant_done":
                    answer = item[1] if isinstance(item[1], str) else ""
                    self.history.append({
                        "id": make_id("a"),
                        "role": "assistant",
                        "content": answer,
                        "at": utc_now(),
                    })
                    self.current_assistant_bubble = None
                    self.busy = False
                    self.set_composer_state(True)
                    self.scroll_to_bottom()
                elif event == "credits":
                    remaining = item[1]
                    if remaining is not None:
                        self.credits.config(text=f"{remaining} credits remaining")
                elif event == "title":
                    title = item[1]
                    self.header_title.config(text=title)
                    self.sidebar_title.config(text=title)
                elif event == "error":
                    self.current_assistant_bubble = None
                    self.busy = False
                    self.set_composer_state(True)
                    messagebox.showerror("Grace", item[1])
        except queue.Empty:
            pass
        self.root.after(40, self.process_ui_queue)


if __name__ == "__main__":
    root = tk.Tk()
    LoginWindow(root)
    root.mainloop()
