---
description: Photorealistic AI render using Flux Pro - preserves geometry, adds environment
---

# Photorealistic AI Render

Uses **Flux Pro** (Black Forest Labs) for photorealistic rendering:
- Preserves exact geometry from input image
- Adds location-appropriate landscaping and environment
- Professional quality output
- No overexposure, natural color grading

## Usage
```
/render                                    # Default settings
/render --location southwest_desert        # Desert style
/render --model canny                      # Edge-based (vs depth)
/render --guidance 40                      # More prompt adherence
```

## Models
| Model | Best For | Cost |
|-------|----------|------|
| **depth** (default) | 3D geometry, architecture | $0.05 |
| **canny** | Clean lines, floor plans | $0.05 |

## Location Profiles
| Profile | Environment |
|---------|-------------|
| south_florida | Tropical, coastal |
| southwest_desert | Xeriscaping, desert |
| southern_california | Mediterranean, coastal CA |
| default | Generic professional landscaping |

## Parameters
- `--guidance 30` (default): Balance of prompt and structure
- `--guidance 50`: More environment changes
- `--guidance 20`: Stricter structure preservation
- `--steps 50` (default): Maximum quality

$ARGUMENTS

---

When user runs `/render`, execute via the AI render MCP server:
```
mcp__ai-render-mcp__render(image_path="...", prompt="...", $ARGUMENTS)
```

Then:
1. Show the rendered image inline using Read tool
2. Speak brief summary of the render (if voice available)
