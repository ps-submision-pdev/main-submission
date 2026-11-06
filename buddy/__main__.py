"""python3 -m buddy chat --persona <id> [--reset]

Loads .env (model settings) inside this process with python-dotenv; nothing prints the key.
--reset deletes this persona's profile file first (data/profile/<id>.json).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from buddy.chat.cli import ROOT, Session
from buddy.llm import LLMClient
from buddy.profile import profile_path


def main() -> int:
    ap = argparse.ArgumentParser(prog="python3 -m buddy")
    sub = ap.add_subparsers(dest="command", required=True)
    chat = sub.add_parser("chat", help="talk to the buddy in the terminal")
    chat.add_argument("--persona", required=True, help="a personas/<id>.json with a matching data/kb/slices/<id>.json")
    chat.add_argument("--reset", action="store_true", help="forget the saved profile and start again")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    path = profile_path(args.persona)
    if args.reset and Path(path).exists():
        Path(path).unlink()
    session = Session(args.persona, LLMClient(timeout=120))
    print("buddy>", session.start())
    while not session.done:
        try:
            message = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbuddy> Bye. Your profile is saved.")
            return 0
        if message:
            result = session.handle(message)
            print(f"buddy [{result['by']}, {result['tokens']['total_tokens']} tokens]>", result["reply"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
