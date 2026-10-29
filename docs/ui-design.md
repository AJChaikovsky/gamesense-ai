# UI design

GameSense has two surfaces with opposite goals. The **overlay** has to be glanceable and quiet. The **dashboard** can take its time and go deep.

## Overlay (in-game)

A transparent, click-through, always-on-top Electron window covering the game.

**Principles**

1. **One tip at a time.** At most one card is visible, and anything else waits in a queue. A newer high-priority tip replaces a low-priority one.
2. **Readable in half a second.** A headline of 8 words or fewer, an optional detail line, and a category icon. For example, a "Heal before the next fight" card with a small "Health 18%" detail line.
3. **Expires on time.** Each tip carries `expires_in_seconds`, shown as a thin progress bar. If the stale-result validator says the situation has changed, the card disappears early.
4. **Stays out of the way.** The default position is upper-right, away from FPS crosshairs, minimaps and most RPG health bars. Each game adapter can suggest a safe zone, and the player can drag it to any of 6 anchor points in settings.
5. **Priority shows without screaming.** A colored left edge marks priority: info is neutral, important is amber, urgent is red. There's no flashing and no sound by default.
6. **Silence is normal.** There's no "AI is thinking" indicator in the game. A small status dot in the corner (green for active, grey for paused, red for offline) is the only constant element, and it can be hidden.

**Hotkeys** (global, rebindable, never conflicting with the game's defaults):

- Dismiss the current tip
- Mark the tip useful or not useful. These are our most valuable quality labels, so they go straight into evals.
- Pause or resume coaching
- Mark this moment for the session review

**Accessibility:** font scale from 80 to 200%, a high-contrast mode, opacity control, and a reduced-motion mode that turns off slide-in animations.

## Dashboard (between sessions)

A normal window opened from the tray.

| Screen | Contents |
| --- | --- |
| Onboarding | Capture consent, game detection, a borderless-mode check, overlay position test, coaching intensity (low, adaptive, high) |
| Home | Last session summary, top 3 focus areas, trend sparkline |
| Session review | A timeline of observations and tips with useful/not-useful marks, key moments with optional keyframes, and an AI summary with evidence links |
| Skill profile | Skill categories with estimated level and uncertainty. Each assessment links to its supporting observations and can be challenged or reset |
| Games | Supported games and their tier, the live-coaching policy status, and the knowledge pack version |
| Settings | Model budget and usage meter, capture rate, hotkeys, overlay appearance, data and privacy (view, export, delete everything) |

**Visual direction:** dark by default to match gaming setups, one accent color, and generous spacing. shadcn/ui components and Lucide icons. The dashboard can be richer, but the overlay uses the same type scale and colors so the two feel like one product.
