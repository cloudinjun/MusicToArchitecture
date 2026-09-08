# TouchDesigner as compute support (MCP)

TouchDesigner is on this machine (`C:/Program Files/Derivative/TouchDesigner`, build
2025.32820, Python 3.11). It is the best audio-visual lab there is, and this folder
lets an agent use it as one: a Web Server DAT inside TouchDesigner speaks the Model
Context Protocol (Streamable HTTP, JSON-RPC over POST) on port 9988, and Claude Code
is pointed at it.

Nothing is downloaded. `td_mcp_callbacks.py` is the whole server, ~200 lines, written
for this project; read it before trusting it. The published alternatives —
[johnsabath/touchdesigner-mcp](https://github.com/johnsabath/touchdesigner-mcp)
(in-TD, 12 tools, MP4 export), [aliphi/touchdesigner-mcp](https://github.com/aliphi/touchdesigner-mcp)
(Node outside, Web Server DAT inside), [8beeeaaat/touchdesigner-mcp](https://github.com/8beeeaaat/touchdesigner-mcp),
[michaelslain/touchdesigner-mcp](https://github.com/michaelslain/touchdesigner-mcp)
(TCP 9005 via a CLI) — all take the same shape; the in-TD one is the shape chosen here,
because it has the fewest moving parts.

## Install, once

1. Start TouchDesigner (any project).
2. Open the textport (`Alt+T`) and run:

   ```python
   exec(open(r'D:/School/sciarc/ATStudioTwo/MusicToArchitecture/tools/td_mcp/bootstrap.py').read())
   ```

   This builds `/mcp` (a Base COMP with the callbacks DAT and the Web Server DAT, port
   9988, active) and saves the project as `tools/td_mcp/mcp_host.toe`.
3. Register the server with Claude Code (user scope — a persistent setting, so it is
   run by hand, once):

   ```bash
   claude mcp add --transport http touchdesigner http://localhost:9988/mcp -s user
   ```

From then on, start TouchDesigner with the saved host and it answers at once:

```bash
"C:/Program Files/Derivative/TouchDesigner/bin/TouchDesigner.exe" "D:/School/sciarc/ATStudioTwo/MusicToArchitecture/tools/td_mcp/mcp_host.toe"
```

`*.toe` in this folder is ignored by git (binary, machine-specific; TouchDesigner
also writes a versioned `mcp_host.1.toe` on save); the two `.py` files are the source
of truth. Re-run the bootstrap after editing the callbacks.

Verified 2026-09-07 against build 2025.32820: `/health`, `initialize`, `tools/list`,
all five tools, and `/run` answer; a `td_snapshot` wrote a PNG. One thing learned:
the **Audio File In CHOP is time-sliced** — it holds one frame's buffer (0.2 s) and is
meant to play in real time — so a *whole-piece* analysis goes through the **File In
CHOP** (WAV/AIFF; convert an MP3 with ffmpeg first), whose output is the entire file,
and an Audio Spectrum CHOP on that is the spectrum of the whole recording.

## Tools

| Tool | Does |
|---|---|
| `td_run` | `exec` Python inside TD; assign to `result` to return a value, stdout comes back too |
| `td_list` | operators under a parent, by glob |
| `td_inspect` | one operator: family, type, parameters, wiring, data summary |
| `td_chop` | a CHOP's channels as arrays |
| `td_snapshot` | save a TOP to PNG/JPG/EXR |

Plain HTTP for scripts in the same session, no MCP client needed:

```bash
curl -s http://localhost:9988/health
curl -s -X POST http://localhost:9988/run --data-binary "result = app.build"
```

## What it is for here

Design studies, not runtime. The web workbench computes its own hearing
(`web/lib/hearing.ts`) and must keep doing so for any upload; TouchDesigner is where a
motion idea is tried at full quality first — Audio Spectrum CHOP → CHOP to TOP → Trace
SOP (contours out of a spectrogram), Optical Flow, Blob Track, instancing — and where
reference frames are rendered for `docs/sound_strip_references.md`. Everything runs on
TD's main thread in the frame the request lands in, so keep calls short.
