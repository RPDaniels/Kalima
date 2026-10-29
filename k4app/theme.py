"""Colores, tipografías y estilo ttk de la aplicación."""
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

BG = "#f3f2ee"          # fondo de la ventana
PANEL = "#ffffff"       # paneles y tablas
FG = "#22252a"
MUTED = "#6c7179"
BORDER = "#d8d5cc"
ACCENT = "#1f6f8b"
ACCENT_DARK = "#174f63"
ACCENT_SOFT = "#dbeaf0"
STRIPE = "#f8f7f4"
WARN = "#a8480b"
OK = "#2e7d4f"

# Colores para S1..S4 / F1-F2 y para las 8 secciones de un Multi
SERIES = ["#1f6f8b", "#c2410c", "#4d7c0f", "#7c3aed", "#be185d", "#0e7490", "#a16207", "#475569"]


def setup(root: tk.Tk) -> dict:
    """Configura el tema y devuelve las fuentes con nombre."""
    style = ttk.Style(root)
    style.theme_use("clam")

    base = tkfont.nametofont("TkDefaultFont")
    base.configure(size=10)
    tkfont.nametofont("TkTextFont").configure(size=10)
    fonts = {
        "base": base,
        "bold": tkfont.Font(root, family=base.actual("family"), size=10, weight="bold"),
        "small": tkfont.Font(root, family=base.actual("family"), size=9),
        "title": tkfont.Font(root, family=base.actual("family"), size=16, weight="bold"),
        "section": tkfont.Font(root, family=base.actual("family"), size=10, weight="bold"),
        "mono": tkfont.Font(root, family=tkfont.nametofont("TkFixedFont").actual("family"), size=10),
    }

    root.configure(bg=BG)
    style.configure(".", background=BG, foreground=FG, bordercolor=BORDER,
                    lightcolor=BG, darkcolor=BORDER, focuscolor=ACCENT)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Panel.TLabel", background=PANEL)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=fonts["small"])
    style.configure("Key.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Value.TLabel", background=PANEL, foreground=FG)
    style.configure("Title.TLabel", background=PANEL, foreground=FG, font=fonts["title"])
    style.configure("Section.TLabel", background=PANEL, foreground=ACCENT_DARK, font=fonts["section"])
    style.configure("Status.TLabel", background=BG, foreground=MUTED, font=fonts["small"])
    style.configure("Badge.TLabel", background=ACCENT_SOFT, foreground=ACCENT_DARK,
                    font=fonts["small"], padding=(6, 1))
    style.configure("Warn.TLabel", background=PANEL, foreground=WARN)

    style.configure("TButton", padding=(10, 4), background="#fbfaf7")
    style.map("TButton", background=[("active", "#ecebe5"), ("disabled", BG)],
              foreground=[("disabled", "#a5a8ad")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT_DARK)
    style.map("Accent.TButton", background=[("active", ACCENT_DARK), ("disabled", "#9dbfcb")],
              foreground=[("disabled", "#eef4f6")])
    style.configure("Tool.TButton", padding=(8, 4))
    style.configure("Link.TButton", background=PANEL, foreground=ACCENT, borderwidth=0,
                    padding=(0, 1), relief="flat", font=fonts["base"])
    style.map("Link.TButton", background=[("active", PANEL)], foreground=[("active", ACCENT_DARK)])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure("TNotebook.Tab", padding=(14, 5), background="#e6e4dd")
    style.map("TNotebook.Tab", background=[("selected", PANEL)],
              foreground=[("selected", ACCENT_DARK)])

    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, rowheight=22,
                    bordercolor=BORDER, borderwidth=1)
    style.configure("Treeview.Heading", background="#ebe9e3", foreground=FG,
                    font=fonts["bold"], relief="flat", padding=(4, 3))
    style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
    style.map("Treeview.Heading", background=[("active", "#e0ded6")])
    style.configure("Detail.Treeview", rowheight=21)

    style.configure("TEntry", fieldbackground=PANEL, padding=3)
    style.configure("TCombobox", fieldbackground=PANEL, padding=2)
    style.configure("TLabelframe", background=BG)
    style.configure("TLabelframe.Label", background=BG, foreground=ACCENT_DARK, font=fonts["section"])
    style.configure("TRadiobutton", background=BG)
    style.configure("TCheckbutton", background=BG)
    style.configure("Panel.TCheckbutton", background=PANEL)
    style.map("Panel.TCheckbutton", background=[("active", PANEL)])
    style.configure("TSpinbox", fieldbackground=PANEL, padding=2, arrowsize=11)
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e4e2db",
                    bordercolor=BORDER, thickness=10)
    style.configure("TPanedwindow", background=BG)
    style.configure("Sash", sashthickness=6)
    return fonts
