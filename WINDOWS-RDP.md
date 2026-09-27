# Running AquaMark on Windows (RDP)

The bundle is Linux-first (static ffmpeg + offline Pillow wheels). On a
Windows RDP machine you need **two free installs** — Python and ffmpeg —
then it's double-click and go.

## 1. Copy the folder

Copy the whole `aquamark-bot` folder to the RDP machine (zip it, then
transfer via RDP clipboard/drive sharing, or download/upload).

Your `.env` (token, OWNER_ID) is already inside — nothing to configure.

## 2. Install Python (once)

1. Download from <https://www.python.org/downloads/> (3.12.x recommended).
2. Run the installer — **tick "Add python.exe to PATH"** on the first screen.
3. Finish.

## 3. Install ffmpeg (once)

Open **PowerShell** or **Command Prompt** and run:

```
winget install --id Gyan.FFmpeg
```

(Windows 10/11 includes `winget`. No winget? Download
`ffmpeg-release-essentials.zip` from <https://www.gyan.dev/ffmpeg/builds/>,
extract, and copy `bin\ffmpeg.exe` into the `aquamark-bot\bin` folder —
or anywhere on PATH.)

Then **close and reopen** the terminal so PATH refreshes.

> The first start also installs Pillow once (small download, needs internet).

## 4. Start the bot

Double-click **`start_bot.bat`** in the folder. It runs the preflight check
and, if everything is green, starts the bot.

Manual alternative:

```
cd C:\path\to\aquamark-bot
python bot.py --check     (everything should be ✓)
python bot.py
```

## 5. Keeping it running on RDP

- **Close the RDP window with the ✕ button (Disconnect)** — do NOT click
  "Sign out". A disconnected session keeps your programs running.
- To check on the bot later, reconnect to the same session.
- If the provider restarts the machine, just run `start_bot.bat` again.

**Auto-start on boot (optional):** press `Win+R`, type `shell:startup`,
press Enter, and put a shortcut to `start_bot.bat` in that folder. The bot
then starts whenever Windows starts. (For a fully invisible service, use
[NSSM](https://nssm.cc): `nssm install Aquamark "C:\...\python.exe" "bot.py"`
with the startup directory set to the bot folder.)

## Running the test suite on Windows

```
cd C:\path\to\aquamark-bot
python -m unittest discover -s . -p "test_*.py"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python with "Add to PATH" ticked, or use `py bot.py` |
| Preflight: `✗ ffmpeg` | `winget install --id Gyan.FFmpeg`, reopen terminal, re-run |
| Bot starts then can't connect | The machine must reach `api.telegram.org:443`; if Telegram is blocked on that network the bot needs a proxy — ask the developer to add proxy support |
| Pillow install fails offline | `pip install Pillow` once on any machine with internet, or copy the `vendor` folder from a machine where it worked |

---

*Prefer Linux? On any Linux x86_64 VPS no installs at all are needed:
`python3 bot.py` and nothing else.*
