# Demo Recording Instructions

This directory contains everything needed to record, convert, and publish a
terminal demo of Cadre AI.

---

## Files

| File | Description |
|---|---|
| `record_demo.sh` | Shell script that records a full asciinema session |
| `demo_output.txt` | Static terminal transcript (for README / docs embedding) |
| `cadre-demo.cast` | Generated asciinema cast file (created by record_demo.sh) |
| `cadre-demo.gif` | Generated GIF (created by conversion step) |

---

## Step 1 — Install Recording Tools

### asciinema (terminal recorder)

```bash
# Ubuntu / Debian / WSL
sudo apt install asciinema

# macOS
brew install asciinema

# pip
pip install asciinema
```

### expect (scripted input driver)

```bash
# Ubuntu / Debian / WSL
sudo apt install expect

# macOS
brew install expect
```

### agg (asciinema to GIF converter — recommended)

```bash
# Download the binary from: https://github.com/asciinema/agg/releases
# Place it on your PATH, then:
agg --version
```

### svg-term-cli (alternative: animated SVG)

```bash
npm install -g svg-term-cli
```

---

## Step 2 — Record the Demo

```bash
chmod +x demo/record_demo.sh
./demo/record_demo.sh
```

This will:
1. Spawn a shell via `expect`
2. Simulate five demo scenes with realistic typing speed
3. Save the recording to `demo/cadre-demo.cast`

The terminal is set to 110 columns x 30 rows — a clean size for GitHub
embeds and YouTube thumbnails.

---

## Step 3 — Convert to GIF

```bash
agg demo/cadre-demo.cast demo/cadre-demo.gif
```

Optional flags:

```bash
# Control playback speed (1.0 = real-time, 2.0 = 2x speed)
agg --speed 1.5 demo/cadre-demo.cast demo/cadre-demo.gif

# Set font size
agg --font-size 14 demo/cadre-demo.cast demo/cadre-demo.gif

# Limit frame rate (smaller file)
agg --fps-cap 15 demo/cadre-demo.cast demo/cadre-demo.gif
```

---

## Step 4 (Optional) — Convert to SVG Animation

SVG animations look sharper than GIFs and are supported in GitHub READMEs.

```bash
svg-term \
  --in  demo/cadre-demo.cast \
  --out demo/cadre-demo.svg \
  --window \
  --width 110 \
  --height 30
```

Then embed in the README:

```markdown
![Cadre AI demo](demo/cadre-demo.svg)
```

---

## Step 5 (Optional) — Convert to MP4

For YouTube, X (Twitter), or LinkedIn:

```bash
agg --speed 1.5 demo/cadre-demo.cast /tmp/cadre-demo.gif
ffmpeg -i /tmp/cadre-demo.gif \
       -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
       -pix_fmt yuv420p \
       demo/cadre-demo.mp4
```

---

## Customizing the Demo Script

The five scenes in `record_demo.sh` map to:

| Scene | Shows |
|---|---|
| 1 | `cadre doctor` — health check output |
| 2 | `cadre install --minimal` — install flow |
| 3 | `/prime` in a project directory |
| 4 | Memory recall in a fresh session |
| 5 | Common sense block + correction capture |

To adjust typing speed, edit the `set send_human` line in the embedded
expect script. Format is `{min max spike burst delay}`.

To change terminal dimensions, edit the `--cols` and `--rows` flags passed
to `asciinema rec`.

---

## Uploading to asciinema.org (optional)

```bash
asciinema upload demo/cadre-demo.cast
```

This gives you a shareable link that can be embedded as a player in the
README using the asciinema badge link format.
