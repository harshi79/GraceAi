"""A functional-enough ``tkinter`` stub so the GUI layer can be exercised
without a display.

The sandbox has no ``tkinter`` build and no X server, so the real toolkit is
unavailable.  This stub implements the subset of the Tk API that
``grace.ui`` actually uses - with real return types where the code depends on
them (``winfo_children`` returns a list, ``Text.index`` returns a string,
``Text.count`` returns an int, ...) and no-ops everywhere else.

It is *not* a layout engine: it proves the GUI code constructs, mutates and
tears down without raising, which is the part that is otherwise untestable
here.  Visual layout, real scrolling and pixel appearance must be verified on
a machine with a display and are reported as such in the README.
"""

from __future__ import annotations

import sys
import types


class _Anything:
    """Permissive return value for unspecified attribute access."""

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    def __call__(self, *args, **kwargs):
        return _Anything()

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return False

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __str__(self):
        return ""

    def __repr__(self):  # pragma: no cover - debugging aid
        return "<stub>"

    def __getitem__(self, item):
        return _Anything()

    def __setitem__(self, key, value):
        pass

    def __contains__(self, item):
        return False

    def __add__(self, other):
        return 0

    def __radd__(self, other):
        return 0


class _Widget:
    """Base stub widget."""

    def __init__(self, master=None, cnf=None, **kw):
        self.master = master
        self._cnf = dict(cnf or {})
        self._cnf.update(kw)
        self._children = []
        self._bindings = {}
        self._after_jobs = {}
        self._after_seq = 0
        self._packed = False
        self._gridded = False
        self._destroyed = False
        self._text = ""
        self._tags = {}
        self._tag_bindings = {}
        self._state = "normal"
        if master is not None and hasattr(master, "_children"):
            master._children.append(self)

    # -- configuration ------------------------------------------------ #
    def configure(self, cnf=None, **kw):
        if cnf:
            self._cnf.update(cnf)
        self._cnf.update(kw)
        return None

    config = configure

    def cget(self, key):
        return self._cnf.get(key, "")

    # -- geometry ----------------------------------------------------- #
    def pack(self, *args, **kw):
        self._packed = True
        return None

    def pack_forget(self):
        self._packed = False

    def pack_propagate(self, flag):
        return None

    def grid(self, *args, **kw):
        self._gridded = True
        return None

    def grid_forget(self):
        self._gridded = False

    def grid_propagate(self, flag):
        return None

    def grid_remove(self):
        self._gridded = False

    def place(self, *args, **kw):
        return None

    def destroy(self):
        self._destroyed = True
        parent = getattr(self, "master", None)
        if parent is not None and hasattr(parent, "_children"):
            try:
                parent._children.remove(self)
            except ValueError:
                pass

    def lift(self):
        return None

    def lower(self):
        return None

    def update(self):
        return None

    def update_idletasks(self):
        return None

    # -- introspection ------------------------------------------------ #
    def winfo_children(self):
        return list(self._children)

    def winfo_parent(self):
        return ""

    def winfo_toplevel(self):
        node = self
        while getattr(node, "master", None) is not None:
            node = node.master
        return node

    def winfo_class(self):
        return type(self).__name__

    def winfo_exists(self):
        return 1

    def winfo_ismapped(self):
        return 1

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def winfo_reqwidth(self):
        return 100

    def winfo_reqheight(self):
        return 30

    def winfo_rootx(self):
        return 0

    def winfo_rooty(self):
        return 0

    def winfo_pointerx(self):
        return 0

    def winfo_pointery(self):
        return 0

    def winfo_containing(self, x, y):
        return None

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080

    # -- events ------------------------------------------------------- #
    def bind(self, sequence=None, func=None, add=None):
        self._bindings.setdefault(sequence, []).append(func)
        return lambda: None

    def unbind(self, sequence, funcid=None):
        self._bindings.pop(sequence, None)

    def bind_all(self, sequence=None, func=None, add=None):
        return lambda: None

    def unbind_all(self, sequence):
        return None

    def event_generate(self, *args, **kw):
        return None

    def focus_set(self):
        return None

    def focus_force(self):
        return None

    def grab_set(self):
        return None

    def grab_release(self):
        return None

    def transient(self, master=None):
        return None

    # -- scheduling --------------------------------------------------- #
    def after(self, ms, func=None, *args):
        self._after_seq += 1
        token = f"after#{self._after_seq}"
        if func is not None:
            self._after_jobs[token] = (func, args)
        return token

    def after_cancel(self, token):
        self._after_jobs.pop(token, None)

    def after_idle(self, func, *args):
        return self.after(0, func, *args)

    def run_after_jobs(self):
        jobs = list(self._after_jobs.values())
        self._after_jobs.clear()
        for func, args in jobs:
            func(*args)

    # -- clipboard ---------------------------------------------------- #
    def clipboard_clear(self):
        return None

    def clipboard_append(self, text):
        return None

    def clipboard_get(self):
        return ""

    def selection_get(self):
        return ""

    def selection_clear(self):
        return None

    # -- fallback ----------------------------------------------------- #
    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return _Anything()


class Tk(_Widget):
    def __init__(self, *args, **kw):
        super().__init__(None, **kw)
        self._title = ""
        self._geometry = ""
        self._attributes = {}
        self._state = "normal"
        self._all_bindings = {}
        self._closed = False

    def title(self, text=None):
        if text is not None:
            self._title = text
        return self._title

    def geometry(self, spec=None):
        if spec is not None:
            self._geometry = spec
        return self._geometry

    def attributes(self, *args, **kw):
        if args:
            self._attributes[args[0]] = args[1] if len(args) > 1 else None
        return None

    def state(self):
        return self._state

    def wm_state(self, state=None):
        if state:
            self._state = state
        return self._state

    def minsize(self, w=None, h=None):
        return None

    def maxsize(self, w=None, h=None):
        return None

    def resizable(self, w=None, h=None):
        return None

    def protocol(self, name, func):
        return None

    def iconphoto(self, *args, **kw):
        return None

    def iconbitmap(self, *args, **kw):
        return None

    def mainloop(self, n=0):
        return None

    def quit(self):
        return None

    def destroy(self):
        self._closed = True

    def option_add(self, *args, **kw):
        return None

    def option_get(self, *args, **kw):
        return ""

    def report_callback_exception(self, *args):
        return None

    def unbind_all(self, sequence):
        return None

    def bind_all(self, sequence=None, func=None, add=None):
        self._all_bindings.setdefault(sequence, []).append(func)
        return lambda: None

    def call(self, *args, **kw):
        return _Anything()


class Toplevel(_Widget):
    def __init__(self, master=None, cnf=None, **kw):
        super().__init__(master, cnf, **kw)
        self._geometry = ""
        self._overrideredirect = False

    def title(self, text=None):
        return text or ""

    def geometry(self, spec=None):
        if spec is not None:
            self._geometry = spec
        return self._geometry

    def overrideredirect(self, flag=None):
        if flag is not None:
            self._overrideredirect = bool(flag)
        return self._overrideredirect

    def withdraw(self):
        return None

    def deiconify(self):
        return None


class Frame(_Widget):
    pass


class Label(_Widget):
    def __init__(self, master=None, cnf=None, **kw):
        super().__init__(master, cnf, **kw)
        self._text = kw.get("text", "")

    def configure(self, cnf=None, **kw):
        if "text" in kw:
            self._text = kw["text"]
        return super().configure(cnf, **kw)

    config = configure


class Button(Label):
    def invoke(self):
        return None


class Entry(_Widget):
    def __init__(self, master=None, cnf=None, **kw):
        super().__init__(master, cnf, **kw)
        self._text = ""

    def get(self):
        return self._text

    def insert(self, index, text):
        self._text += str(text)

    def delete(self, first, last=None):
        self._text = ""

    def icursor(self, index):
        return None

    def selection_range(self, start, end):
        return None


class Text(_Widget):
    def __init__(self, master=None, cnf=None, **kw):
        super().__init__(master, cnf, **kw)
        self._lines = [""]
        self._tags = {}
        self._tag_config = {}
        self._windows = []

    # -- content ------------------------------------------------------ #
    def insert(self, index, chars, *args):
        text = chars if isinstance(chars, str) else str(chars)
        for tag in args:
            if isinstance(tag, str):
                self._tags.setdefault(tag, [])
        if self._is_end(index) or str(index).startswith("end"):
            self._lines[-1] += text
        else:
            self._lines[0] += text
        return None

    def delete(self, first, last=None):
        if self._is_start(first) and (last is None or self._is_end(last)):
            self._lines = [""]
        return None

    @staticmethod
    def _is_start(spec):
        return str(spec) in ("1.0", "0.0", "insert", "start")

    @staticmethod
    def _is_end(spec):
        text = str(spec)
        return text == "end" or text.startswith("end ")

    def get(self, first, last=None):
        if self._is_start(first) and (last is None or self._is_end(last)):
            return "\n".join(self._lines)
        return ""

    def index(self, spec):
        if self._is_end(spec):
            return f"{len(self._lines)}.{len(self._lines[-1])}"
        return str(spec)

    def compare(self, a, op, b):
        return False

    def see(self, index):
        return None

    def mark_set(self, name, index):
        return None

    def count(self, start, end, *opts):
        return 1

    def search(self, *args, **kw):
        return None

    def dump(self, *args, **kw):
        return ()

    # -- tags --------------------------------------------------------- #
    def tag_add(self, tag, first, last=None):
        self._tags.setdefault(tag, []).append((first, last))
        return None

    def tag_remove(self, tag, first, last=None):
        return None

    def tag_configure(self, tag, **kw):
        self._tag_config[tag] = kw
        return None

    def tag_bind(self, tag, sequence, func, add=None):
        self._tag_bindings.setdefault(tag, {})[sequence] = func
        return None

    def tag_cget(self, tag, option):
        return self._tag_config.get(tag, {}).get(option, "")

    def tag_ranges(self, tag):
        return ()

    def tag_names(self, index=None):
        return tuple(self._tags)

    def tag_nextrange(self, tag, first, last=None):
        return None

    # -- embedded windows --------------------------------------------- #
    def window_create(self, index, **kw):
        self._windows.append((index, kw))
        return None

    def window_configure(self, window, **kw):
        return None

    # -- scrolling ---------------------------------------------------- #
    def yview(self, *args):
        return (0.0, 1.0)

    def yview_moveto(self, fraction):
        return None

    def yview_scroll(self, number, what):
        return None

    def xview(self, *args):
        return (0.0, 1.0)

    def configure(self, cnf=None, **kw):
        if "height" in kw and isinstance(kw["height"], int):
            pass
        return super().configure(cnf, **kw)

    config = configure


class Canvas(_Widget):
    def create_polygon(self, *args, **kw):
        return 1

    def create_text(self, *args, **kw):
        return 1

    def create_oval(self, *args, **kw):
        return 1

    def create_rectangle(self, *args, **kw):
        return 1

    def create_line(self, *args, **kw):
        return 1

    def create_window(self, *args, **kw):
        return 1

    def create_image(self, *args, **kw):
        return 1

    def delete(self, *args):
        return None

    def itemconfigure(self, item, **kw):
        return None

    def itemcget(self, item, option):
        return ""

    def bbox(self, *args):
        return (0, 0, 100, 100)

    def yview(self, *args):
        return (0.0, 1.0)

    def yview_moveto(self, fraction):
        return None

    def yview_scroll(self, number, what):
        return None

    def xview(self, *args):
        return (0.0, 1.0)

    def tag_bind(self, tag, sequence, func, add=None):
        return None


class Scrollbar(_Widget):
    def set(self, first, last):
        return None

    def get(self):
        return (0.0, 1.0)


class Menu(_Widget):
    def add_command(self, **kw):
        return None

    def add_separator(self, **kw):
        return None

    def post(self, x, y):
        return None

    def unpost(self):
        return None


class PhotoImage(_Widget):
    def __init__(self, master=None, cnf=None, **kw):
        super().__init__(master, cnf, **kw)


class Variable(_Widget):
    def __init__(self, master=None, value=None, name=None):
        super().__init__(master)
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class StringVar(Variable):
    pass


class BooleanVar(Variable):
    pass


class IntVar(Variable):
    pass


class DoubleVar(Variable):
    pass


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

END = "end"
INSERT = "insert"
CURRENT = "current"
ANCHOR = "anchor"
SEL = "sel"
SEL_FIRST = "sel.first"
SEL_LAST = "sel.last"
WORD = "word"
CHAR = "char"
NONE = "none"
FLAT = "flat"
RAISED = "raised"
SUNKEN = "sunken"
GROOVE = "groove"
RIDGE = "ridge"
LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
CENTER = "center"
BOTH = "both"
X = "x"
Y = "y"
N = "n"
S = "s"
E = "e"
W = "w"
NE = "ne"
NW = "nw"
SE = "se"
SW = "sw"
NSEW = "nsew"
NS = "ns"
EW = "ew"
HORIZONTAL = "horizontal"
VERTICAL = "vertical"
NORMAL = "normal"
DISABLED = "disabled"
ACTIVE = "active"
HIDDEN = "hidden"
TRUE = True
FALSE = False


class _EventType:
    Enter = 7
    Leave = 8
    ButtonPress = 4
    ButtonRelease = 5
    Motion = 6
    KeyPress = 2
    KeyRelease = 3
    Configure = 22
    FocusIn = 9
    FocusOut = 10
    MouseWheel = 38


EventType = _EventType


# --------------------------------------------------------------------------- #
# font submodule
# --------------------------------------------------------------------------- #


class Font:
    FAMILIES = [
        "Inter", "Segoe UI", "Ubuntu", "Cantarell", "Noto Sans",
        "DejaVu Sans", "Helvetica", "JetBrains Mono", "Consolas",
        "Ubuntu Mono", "DejaVu Sans Mono", "Courier New",
    ]

    def __init__(self, root=None, name=None, exists=False, **kw):
        self._kw = kw

    def configure(self, **kw):
        self._kw.update(kw)

    config = configure

    def cget(self, option):
        return self._kw.get(option, "")

    def measure(self, text):
        return len(str(text)) * 7

    def metrics(self, *args, **kw):
        return {"ascent": 10, "descent": 3, "linespace": 14}

    def actual(self, option=None, displayof=None):
        return dict(self._kw)

    def names(self):
        return []

    def copy(self):
        return Font(**self._kw)

    def __eq__(self, other):
        return isinstance(other, Font) and other._kw == self._kw

    def __hash__(self):
        return hash(tuple(sorted(self._kw.items(), key=lambda kv: kv[0])))


def families(root=None, displayof=None):
    return list(Font.FAMILIES)


def nametofont(name, root=None):
    return Font()


def exists(font, root=None):
    return True


font_module = types.ModuleType("tkinter.font")
font_module.Font = Font
font_module.families = families
font_module.nametofont = nametofont
font_module.exists = exists


# --------------------------------------------------------------------------- #
# filedialog / messagebox / simpledialog
# --------------------------------------------------------------------------- #

filedialog = types.ModuleType("tkinter.filedialog")
filedialog.askopenfilenames = lambda **kw: ()
filedialog.askopenfilename = lambda **kw: ""
filedialog.asksaveasfilename = lambda **kw: ""
filedialog.askdirectory = lambda **kw: ""

messagebox = types.ModuleType("tkinter.messagebox")
messagebox.showinfo = lambda *a, **kw: "ok"
messagebox.showwarning = lambda *a, **kw: "ok"
messagebox.showerror = lambda *a, **kw: "ok"
messagebox.askyesno = lambda *a, **kw: True
messagebox.askokcancel = lambda *a, **kw: True
messagebox.askretrycancel = lambda *a, **kw: True

simpledialog = types.ModuleType("tkinter.simpledialog")
simpledialog.askstring = lambda *a, **kw: ""

colorchooser = types.ModuleType("tkinter.colorchooser")
colorchooser.askcolor = lambda *a, **kw: ((0, 0, 0), "#000000")

scrolledtext = types.ModuleType("tkinter.scrolledtext")
scrolledtext.ScrolledText = Text

ttk = types.ModuleType("tkinter.ttk")


class _TtkWidget(_Widget):
    pass


ttk.Frame = _TtkWidget
ttk.Label = _TtkWidget
ttk.Button = _TtkWidget
ttk.Entry = _TtkWidget
ttk.Scrollbar = _TtkWidget
ttk.Style = _TtkWidget
ttk.Notebook = _TtkWidget
ttk.Treeview = _TtkWidget
ttk.Combobox = _TtkWidget
ttk.Progressbar = _TtkWidget
ttk.Separator = _TtkWidget
ttk.Spinbox = _TtkWidget
ttk.Checkbutton = _TtkWidget
ttk.Radiobutton = _TtkWidget
ttk.Scale = _TtkWidget
ttk.Panedwindow = _TtkWidget
ttk.Labelframe = _TtkWidget
ttk.Sizegrip = _TtkWidget


# --------------------------------------------------------------------------- #
# Installation
# --------------------------------------------------------------------------- #


def build_module():
    module = types.ModuleType("tkinter")
    for name in (
        "Tk", "Toplevel", "Frame", "Label", "Button", "Entry", "Text", "Canvas",
        "Scrollbar", "Menu", "Menubutton", "PhotoImage", "Variable", "StringVar",
        "BooleanVar", "IntVar", "DoubleVar", "Spinbox", "Listbox", "Checkbutton",
        "Radiobutton", "Scale", "PanedWindow", "LabelFrame", "Message",
        "OptionMenu", "BitmapmapImage", "Image",
    ):
        if hasattr(sys.modules[__name__], name):
            setattr(module, name, getattr(sys.modules[__name__], name))
        else:
            setattr(module, name, _Widget)
    module.Widget = _Widget
    module.Misc = _Widget

    for name in dir(sys.modules[__name__]):
        if name.isupper() or name == "EventType":
            setattr(module, name, getattr(sys.modules[__name__], name))

    module.font = font_module
    module.filedialog = filedialog
    module.messagebox = messagebox
    module.simpledialog = simpledialog
    module.colorchooser = colorchooser
    module.scrolledtext = scrolledtext
    module.ttk = ttk
    module.TclError = type("TclError", (Exception,), {})
    return module


def install():
    """Install the stub into ``sys.modules``.  Returns the stub module."""
    module = build_module()
    sys.modules["tkinter"] = module
    sys.modules["tkinter.font"] = font_module
    sys.modules["tkinter.filedialog"] = filedialog
    sys.modules["tkinter.messagebox"] = messagebox
    sys.modules["tkinter.simpledialog"] = simpledialog
    sys.modules["tkinter.colorchooser"] = colorchooser
    sys.modules["tkinter.scrolledtext"] = scrolledtext
    sys.modules["tkinter.ttk"] = ttk
    return module
