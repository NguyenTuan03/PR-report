#!/opt/homebrew/bin/python3
"""
App GUI: fetch tiêu đề commit từ PR GitHub của bạn (từ 00:00 hôm nay), rồi nhờ Claude
tóm tắt tất cả thành 3-4 dòng. Bản tóm tắt tự copy vào clipboard.

Yêu cầu: `gh auth login`, và `claude` (Claude Code CLI) hoặc `agy` (Antigravity CLI) đã login.
Chạy: /opt/homebrew/bin/python3 daily_report.py
(Không dùng /usr/bin/python3 của Apple: Tk 8.5 cũ, cửa sổ hiện trắng trơn.)
"""

import json
import os
import queue
import shutil
import subprocess
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Mở từ Finder/VS Code thì PATH có thể thiếu Homebrew -> không tìm thấy `gh`.
os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

executor = ThreadPoolExecutor(max_workers=1)

# Bảng màu, tím khớp với icon.
BG = "#F4F3F8"
CARD = "#FFFFFF"
BORDER = "#E4E2EE"
TEXT = "#1C1B22"
MUTED = "#76748A"
ACCENT = "#7C3AED"
ACCENT_HOVER = "#6D28D9"
ACCENT_SOFT = "#EDE7FD"
DISABLED = "#B9A6F0"
ERROR = "#C62828"
SUMMARY_BG = "#F7F3FF"
SUMMARY_BORDER = "#DCCFFB"


def gh_json(args: list[str]):
    out = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True
    ).stdout
    return json.loads(out)


def fetch_commit_titles(repo: str, number: int, since: datetime) -> list[str]:
    # Chỉ lấy commit tạo từ `since` trở đi, bỏ commit cũ trong cùng PR.
    commits = gh_json(["pr", "view", str(number), "--repo", repo,
                       "--json", "commits"])["commits"]
    return [
        c["messageHeadline"] for c in commits
        if datetime.fromisoformat(c["committedDate"].replace("Z", "+00:00")) >= since
    ]


def fetch_prs() -> list[dict]:
    """PR update hôm nay, mỗi PR kèm các commit hôm nay: {repo, title, commits}."""
    since = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    prs = gh_json(["search", "prs", "--author=@me", f"--updated=>{since.isoformat()}",
                   "--json", "number,repository,title", "--limit", "50"])
    result = []
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        commits = fetch_commit_titles(repo, pr["number"], since)
        if commits:
            result.append({"repo": repo, "title": pr["title"], "commits": commits})
    return result


SUMMARY_PROMPT = (
    "Below are the pull requests I worked on today, each with today's commit titles. "
    "Write a summary for my daily standup in 3 to 4 lines total, covering all PRs together: "
    "group related work, describe outcomes in plain English, skip merges and trivial "
    "comment/doc tweaks unless that's all there is. Each line is one short sentence of at "
    "most 15 words, no code formatting. Output only the lines, each starting with '- ', "
    "no heading or preamble."
)


_login_path: str | None = None


def login_shell_path() -> str:
    """PATH như trong Terminal của người dùng. App mở từ Finder không đọc .zshrc,
    nên thiếu các thư mục như ~/.local/bin mà installer của claude/agy thêm vào."""
    global _login_path
    if _login_path is None:
        try:
            out = subprocess.run(
                [os.environ.get("SHELL", "/bin/zsh"), "-ilc", 'printf "\\n__PATH__=%s" "$PATH"'],
                capture_output=True, text=True, timeout=10,
            ).stdout
            _login_path = out.rsplit("__PATH__=", 1)[1].strip() if "__PATH__=" in out else ""
        except (subprocess.TimeoutExpired, OSError):
            _login_path = ""
    return _login_path


def find_cli(name: str) -> str | None:
    for path in (None, login_shell_path()):
        found = shutil.which(name, path=path)
        # Bỏ qua launcher của app editor (vd `agy` của Antigravity IDE mở cửa sổ editor,
        # không trả lời prompt) và symlink hỏng.
        if found and ".app/Contents/" not in os.path.realpath(found) \
                and os.path.exists(os.path.realpath(found)):
            return found
    return None


class SummaryError(Exception):
    pass


def summarize(prs: list[dict]) -> tuple[list[str], str]:
    """Tóm tắt bằng CLI AI có sẵn trên máy (tài khoản đã login, không cần API key).
    Thử Claude Code trước, lỗi/không có thì sang Antigravity CLI. Trả về (dòng, tên CLI)."""
    body = "\n\n".join(
        f"PR: {p['title']} ({p['repo']})\n" + "\n".join(f"  - {c}" for c in p["commits"])
        for p in prs
    )
    providers = [
        # claude đọc danh sách PR từ stdin.
        ("Claude", "claude", lambda exe: ([exe, "-p", SUMMARY_PROMPT], body)),
        # agy -p không đọc stdin, nên ghép danh sách vào prompt.
        ("Antigravity", "agy", lambda exe: ([exe, "-p", f"{SUMMARY_PROMPT}\n\n{body}"], None)),
    ]
    errors = []
    for label, name, build in providers:
        exe = find_cli(name)
        if not exe:
            errors.append(f"{label}: `{name}` not installed")
            continue
        args, stdin = build(exe)
        try:
            out = subprocess.run(
                args, input=stdin, capture_output=True, text=True, check=True, timeout=180,
                cwd=tempfile.gettempdir(),  # tránh đọc CLAUDE.md/GEMINI.md của thư mục hiện tại
            ).stdout
        except subprocess.TimeoutExpired:
            errors.append(f"{label}: took too long to answer")
            continue
        except subprocess.CalledProcessError as e:
            errors.append(f"{label}: {(e.stderr or e.stdout).strip()[-300:]}")
            continue
        lines = [l.strip().lstrip("-*•").strip() for l in out.splitlines()]
        lines = [l for l in lines if l][:4]
        if lines:
            return lines, label
        errors.append(f"{label}: empty answer")
    raise SummaryError(
        "No AI CLI could summarize. Install and log in to Claude Code (`claude`) "
        "or Antigravity CLI (`agy`).\n\n" + "\n".join(errors)
    )


PARABOL_URL = "https://action.parabol.co"

# Brave dùng chung bộ lệnh AppleScript với Chrome. Nhảy tới tab Parabol đang mở,
# không có thì mở tab mới (hoặc cửa sổ mới nếu Brave chưa có cửa sổ nào).
REVEAL_PARABOL_SCRIPT = f'''
tell application "Brave Browser"
    activate
    set found to false
    repeat with w in windows
        set i to 0
        repeat with t in tabs of w
            set i to i + 1
            if URL of t contains "parabol.co" then
                set active tab index of w to i
                set index of w to 1
                set found to true
                exit repeat
            end if
        end repeat
        if found then exit repeat
    end repeat
    if not found then
        if (count of windows) = 0 then make new window
        tell window 1 to make new tab with properties {{URL:"{PARABOL_URL}"}}
    end if
end tell
'''


def reveal_parabol_tab() -> None:
    # Chạy nền, không chặn UI; lần đầu macOS hỏi quyền "PR Report muốn điều khiển Brave".
    subprocess.Popen(["osascript", "-e", REVEAL_PARABOL_SCRIPT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def format_report(lines: list[str]) -> str:
    # Định dạng paste vào Notion/Parabol.
    return "\n".join(["Today:", "", *(f"* {t}" for t in lines)])


class PillButton(tk.Canvas):
    """Nút bo tròn tự vẽ (nút Tk trên macOS không đổi được màu)."""

    def __init__(self, parent, text: str, command, primary: bool = True, width: int = 112):
        super().__init__(parent, width=width, height=36, bg=BG,
                         highlightthickness=0, cursor="pointinghand")
        self.command, self.primary, self.enabled = command, primary, True
        self.w, self.h = width, 36
        self.font = tkfont.Font(family=BASE_FONT, size=13, weight="bold")
        self.text = text
        self._hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)
        self._draw()

    def _colors(self) -> tuple[str, str, str]:
        if self.primary:
            if not self.enabled:
                return DISABLED, DISABLED, "#FFFFFF"
            fill = ACCENT_HOVER if self._hover else ACCENT
            return fill, fill, "#FFFFFF"
        # Nút phụ: nền tím nhạt, chữ tím (nền trắng dễ lẫn vào nền cửa sổ).
        fill = "#E0D5FC" if self._hover and self.enabled else ACCENT_SOFT
        return fill, "#D4C6FA", ACCENT if self.enabled else MUTED

    def _draw(self) -> None:
        self.delete("all")
        fill, outline, fg = self._colors()
        r, w, h = self.h // 2, self.w - 1, self.h - 1
        # Hình viên thuốc = 2 nửa tròn + hình chữ nhật.
        for x0 in (0, w - 2 * r):
            self.create_oval(x0, 0, x0 + 2 * r, h, fill=fill, outline=outline)
        self.create_rectangle(r, 0, w - r, h, fill=fill, outline="")
        self.create_line(r, 0, w - r, 0, fill=outline)
        self.create_line(r, h, w - r, h, fill=outline)
        self.create_text(self.w // 2, self.h // 2, text=self.text, fill=fg, font=self.font)

    def _set_hover(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def _click(self, _event) -> None:
        if self.enabled:
            self.command()

    def configure_state(self, enabled: bool, text: str | None = None) -> None:
        self.enabled = enabled
        if text:
            self.text = text
        self.config(cursor="pointinghand" if enabled else "arrow")
        self._draw()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        global BASE_FONT
        BASE_FONT = tkfont.nametofont("TkDefaultFont").actual("family")

        self.title("PR Report")
        self.geometry("620x720")
        self.minsize(480, 560)
        self.configure(bg=BG)
        self.list_report = ""
        self.summary_report = ""
        # Tk không an toàn đa luồng: worker bỏ (loại, dữ liệu) vào queue, luồng chính đọc ra.
        self.results: queue.Queue[tuple[str, object]] = queue.Queue()

        # --- Header: tiêu đề, ngày, số commit ---
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 14))
        left = tk.Frame(header, bg=BG)
        left.pack(side="left")
        tk.Label(left, text="Today's commits", bg=BG, fg=TEXT,
                 font=(BASE_FONT, 22, "bold")).pack(anchor="w")
        tk.Label(left, text=datetime.now().strftime("%A, %d %B %Y"), bg=BG, fg=MUTED,
                 font=(BASE_FONT, 13)).pack(anchor="w", pady=(2, 0))
        self.badge = tk.Label(header, text="", bg=ACCENT_SOFT, fg=ACCENT,
                              font=(BASE_FONT, 12, "bold"), padx=12, pady=4)

        # --- Footer: trạng thái + nút. Pack trước các card để luôn có chỗ. ---
        footer = tk.Frame(self, bg=BG)
        footer.pack(side="bottom", fill="x", padx=24, pady=16)
        self.copy_summary_btn = PillButton(footer, "Copy summary", self.on_copy_summary,
                                           primary=False, width=128)
        self.copy_summary_btn.pack(side="right")
        self.copy_list_btn = PillButton(footer, "Copy list", self.on_copy_list,
                                        primary=False, width=96)
        self.copy_list_btn.pack(side="right", padx=(0, 8))
        self.fetch_btn = PillButton(footer, "Fetch PR", self.on_fetch, width=112)
        self.fetch_btn.pack(side="right", padx=(0, 8))
        self.status = tk.Label(footer, text="", bg=BG, fg=MUTED, font=(BASE_FONT, 12),
                               anchor="w")
        self.status.pack(side="left", fill="x", expand=True)

        # --- Card tóm tắt (trên footer, cao cố định) ---
        scard = tk.Frame(self, bg=SUMMARY_BG, highlightbackground=SUMMARY_BORDER,
                         highlightcolor=SUMMARY_BORDER, highlightthickness=1)
        scard.pack(side="bottom", fill="x", padx=24, pady=(14, 0))
        shead = tk.Frame(scard, bg=SUMMARY_BG)
        shead.pack(fill="x", padx=18, pady=(12, 0))
        tk.Label(shead, text="✦ Summary", bg=SUMMARY_BG, fg=ACCENT,
                 font=(BASE_FONT, 14, "bold")).pack(side="left")
        self.summary_by = tk.Label(shead, text="all PRs", bg=SUMMARY_BG, fg=MUTED,
                                   font=(BASE_FONT, 11))
        self.summary_by.pack(side="left", padx=(8, 0), pady=(2, 0))
        self.summary = self._make_text(scard, SUMMARY_BG, height=6)
        self.summary.pack(fill="x")

        # --- Card danh sách commit (chiếm phần còn lại) ---
        card = tk.Frame(self, bg=CARD, highlightbackground=BORDER,
                        highlightcolor=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True, padx=24)
        self.text = self._make_text(card, CARD, height=1)
        self.text.pack(fill="both", expand=True)

        self.bind("<Command-r>", lambda e: self.on_fetch())
        self._show_message(self.text, "Press Fetch PR (⌘R) to load today's commits.", "empty")
        self._show_message(self.summary, "The summary appears here after fetching.", "muted")
        self.after(300, self.on_fetch)  # tự fetch khi mở app

    def _make_text(self, parent, bg: str, height: int) -> tk.Text:
        t = tk.Text(
            parent, width=1, height=height,  # co giãn theo cửa sổ, không đòi 80 ký tự
            wrap="word", bg=bg, fg=TEXT, relief="flat", borderwidth=0,
            highlightthickness=0, padx=18, pady=12, font=(BASE_FONT, 14),
            spacing1=4, spacing3=4, cursor="arrow", selectbackground=ACCENT_SOFT,
            insertwidth=0,
        )
        t.tag_configure("bullet", foreground=ACCENT, font=(BASE_FONT, 14, "bold"))
        t.tag_configure("line", lmargin1=0, lmargin2=22)
        t.tag_configure("empty", foreground=MUTED, justify="center",
                        spacing1=90, font=(BASE_FONT, 14))
        t.tag_configure("muted", foreground=MUTED, font=(BASE_FONT, 13))
        t.tag_configure("error", foreground=ERROR, font=("Menlo", 12))
        t.bind("<Key>", lambda e: None if e.state & 0x8 else "break")  # chỉ đọc, vẫn Cmd+C được
        return t

    # --- Hiển thị ---
    def _show_message(self, widget: tk.Text, msg: str, tag: str) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", msg, tag)

    def _show_lines(self, widget: tk.Text, lines: list[str]) -> None:
        widget.delete("1.0", "end")
        for i, t in enumerate(lines):
            widget.insert("end", "•  ", ("bullet", "line"))
            widget.insert("end", t + ("\n" if i < len(lines) - 1 else ""), "line")

    def _set_badge(self, count: int | None) -> None:
        if count is None:
            self.badge.pack_forget()
        else:
            self.badge.config(text=f"{count} commit{'s' if count != 1 else ''}")
            self.badge.pack(side="right", anchor="n", pady=(6, 0))

    # --- Hành động ---
    def on_fetch(self) -> None:
        if not self.fetch_btn.enabled:
            return
        self.fetch_btn.configure_state(False, "Fetching…")
        self.status.config(text="Loading from GitHub…", fg=MUTED)
        executor.submit(self._fetch_worker)
        self.after(100, self._poll)

    def _fetch_worker(self) -> None:
        put = self.results.put
        try:
            prs = fetch_prs()
        except subprocess.CalledProcessError as e:
            put(("error", f"gh error:\n{e.stderr}"))
            return put(("done", None))
        except Exception as e:  # vd: không tìm thấy `gh`, JSON lỗi
            put(("error", f"Error: {e!r}"))
            return put(("done", None))
        put(("prs", prs))
        if prs:
            try:
                put(("summary", summarize(prs)))
            except SummaryError as e:
                put(("summary_error", str(e)))
        put(("done", None))

    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self.results.get_nowait()
            except queue.Empty:
                self.after(100, self._poll)
                return
            stamp = datetime.now().strftime("%H:%M")
            if kind == "error":
                self.list_report = self.summary_report = ""
                self._set_badge(None)
                self._show_message(self.text, str(payload), "error")
                self._show_message(self.summary, "No summary.", "muted")
                self.status.config(text=f"Failed at {stamp}", fg=ERROR)
            elif kind == "prs":
                titles = [c for p in payload for c in p["commits"]]  # type: ignore[union-attr]
                self.list_report = format_report(titles)
                self.summary_report = ""
                self._set_badge(len(titles))
                if titles:
                    self._show_lines(self.text, titles)
                    self._show_message(self.summary, "Summarizing…", "muted")
                    self.summary_by.config(text="all PRs")
                    self.fetch_btn.configure_state(False, "Summarizing…")
                    self.status.config(text="Summarizing with AI…", fg=MUTED)
                else:
                    self._show_message(self.text, "No commits yet today. 🌱", "empty")
                    self._show_message(self.summary, "Nothing to summarize yet.", "muted")
                    self.status.config(text=f"Updated {stamp}", fg=MUTED)
            elif kind == "summary":
                lines, provider = payload  # type: ignore[misc]
                self.summary_by.config(text=f"all PRs · by {provider}")
                self.summary_report = format_report(lines)
                self._show_lines(self.summary, lines)
                self.on_copy_summary()
                reveal_parabol_tab()
                self.status.config(text=f"✓ Copied · Parabol opened · {stamp}", fg=MUTED)
            elif kind == "summary_error":
                self._show_message(self.summary, str(payload), "error")
                self.status.config(text=f"Summary failed at {stamp}", fg=ERROR)
            elif kind == "done":
                self.fetch_btn.configure_state(True, "Fetch PR")
                return

    def _copy(self, text: str, what: str) -> None:
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.config(text=f"✓ {what} copied · {datetime.now().strftime('%H:%M')}",
                           fg=MUTED)

    def on_copy_list(self) -> None:
        self._copy(self.list_report, "List")

    def on_copy_summary(self) -> None:
        self._copy(self.summary_report, "Summary")

BASE_FONT = "Helvetica Neue"

if __name__ == "__main__":
    App().mainloop()
