"""Privately save a dashboard-issued connector token; never start the connector."""

import argparse
import getpass
import json
import os
import re
import sys
import warnings
from pathlib import Path


def extract_token(entered: str) -> str | None:
    entered = entered.strip()
    match = re.search(r"--token(?:=|\s+)[\"']?([A-Za-z0-9_+/=-]+)", entered)
    if not match:
        match = re.search(r"\bservice\s+install\s+[\"']?([A-Za-z0-9_+/=-]+)", entered)
    token = match.group(1) if match else entered.strip("\"'")
    return token if re.fullmatch(r"[A-Za-z0-9_+/-]{64,8192}={0,2}", token) else None


def gui_input() -> str:
    import tkinter as tk

    window = tk.Tk()
    window.title("I-Stay private Cloudflare token entry")
    window.geometry("760x250")
    window.resizable(False, False)
    tk.Label(window, text="Cloudflare Tunnel Token — 隐藏输入", font=("Segoe UI", 14)).pack(pady=16)
    tk.Label(
        window,
        text="粘贴 Token 或含 Token 的安装命令（Ctrl+V），然后点击保存。\n不会执行命令，也不会启动 Tunnel。",
    ).pack()
    entry = tk.Entry(window, show="*", width=90)
    entry.pack(padx=20, pady=15)
    entry.focus_set()
    message = tk.Label(window, text="", fg="red")
    message.pack()
    saved_input: list[str] = []

    def submit(_event=None):
        token = extract_token(entry.get())
        if token is None:
            message.config(text="未找到有效 Token；请复制含 --token 的 Docker 命令再粘贴。")
            entry.selection_range(0, tk.END)
            entry.focus_set()
            return
        saved_input.append(token)
        window.destroy()

    tk.Button(window, text="保存 Token / Save", command=submit, width=24).pack(pady=8)
    window.bind("<Return>", submit)
    window.mainloop()
    if not saved_input:
        raise EOFError
    return saved_input[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Protected deployment directory")
    parser.add_argument("--status-file", type=Path, help="Optional credential-free result file")
    parser.add_argument(
        "--gui", action="store_true", help="Use a masked paste-friendly entry window"
    )
    args = parser.parse_args()

    def result(code: int, message: str) -> int:
        print(message)
        if args.status_file:
            args.status_file.write_text(
                json.dumps({"exit_code": code, "message": message}), encoding="utf-8"
            )
        return code

    root = args.root.resolve(strict=True)
    secret_dir = root / "secrets" / "production"
    if not (root / ".deployment.json").is_file() or not secret_dir.is_dir():
        return result(2, "Use the existing protected deployment directory.")
    if secret_dir.resolve() != secret_dir or any("onedrive" in p.lower() for p in root.parts):
        return result(2, "Refusing a redirected or OneDrive-synced secrets directory.")
    target = secret_dir / "tunnel_token.txt"
    if target.exists():
        return result(3, "A token file already exists. It was not overwritten.")
    if not args.gui and not sys.stdin.isatty():
        return result(
            2, "Run this script in an interactive local console; input must remain hidden."
        )
    print("Paste the Cloudflare Tunnel token OR its Docker install command below.")
    print("Input is hidden. Press Enter once. Do not send it in chat.")
    try:
        if args.gui:
            entered = gui_input()
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                entered = getpass.getpass("Tunnel token (hidden): ").strip()
        token = extract_token(entered)
        if token is None:
            return result(
                2, "Input was not a token or a connector install command. Nothing was saved."
            )
        # Exclusive creation preserves existing credentials; the protected parent ACL is inherited.
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(token + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return result(
            0, "Token saved privately. No connector was started and no route was published."
        )
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        return result(2, "Cancelled; hidden input is required.")
    except OSError:
        return result(
            2, "Could not save the token. Check the protected folder and file permissions."
        )


if __name__ == "__main__":
    raise SystemExit(main())
