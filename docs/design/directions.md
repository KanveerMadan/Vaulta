# Vaulta: three visual directions

**Design read:** a personal-finance product for salaried Indians whose entire pitch is trust.
- **Showpiece surfaces** (landing, onboarding, Money Wrapped, reports) carry the spectacle.
- **The workspace** (home, transactions, budgets, people, cash, chat, settings) is calm and precise. It earns trust through typography, rhythm and speed.

**Dials.**
| Surface | Variance | Motion | Density |
|---|---|---|---|
| Showpieces | 7 | 7 | 3 |
| Workspace | 4 | 3 | 6 |

**Process note.** The image-to-code skill asks for generated reference images first. This environment has no image-generation tool, so each direction below has a written spec and an ASCII key-screen sketch instead. Per the brief, the landing page's main visual is the real product rendered from demo data, not an image.

Starting point (what exists today):
- **Colour:** a forest-green brand on sage-tinted surfaces.
- **Type:** Fraunces display with Instrument Sans UI.
- **Bugs:** a colour ramp with missing steps (`ink-400/600/800` are referenced 120+ times but not defined, so that text has no colour), and no dark theme.

---

## A. Ledger *(chosen)*

**Idea:** the ruled line of a bank statement is the brand.
- The landing story starts on a real statement's ruled rows.
- In the product, those same rules become the transaction rows, budget tracks and report columns.
- Everything sits on a strict baseline grid, so money lines up like it does in an accountant's ledger.

**Palette.** Cool paper and ink plus one green: the existing brand green, sharpened, not a new identity. No beige, no brass, no gradients.

| Token | Light | Dark |
|---|---|---|
| canvas | `#F4F6F3` cool paper | `#0B0E0C` |
| surface | `#FFFFFF` | `#131815` |
| ink | `#101511` | `#E9EEEA` |
| ink-muted | `#56615A` (6.2:1 on canvas) | `#9BA69E` |
| line | `#D9DFDA` | `#27302A` |
| accent (Vaulta green) | `#17643F` (6.9:1 on white) | `#5CCB93` |
| warning | `#8A5A00` | `#E8B04B` |
| danger | `#B3261E` | `#F2867D` |

**Type pairing.**
- **Bricolage Grotesque** (variable, optical size) for display. At large sizes it has a slightly irregular, hand-set warmth that reads human, not "fintech". At small sizes it calms down.
- **Geist** for UI, with tabular figures (`tnum`) on every amount.
- **Geist Mono** for references and codes.
- All self-hosted.

**Motion language: "rails and settle".**
- Things move in straight lines along the grid (rows slide on their rail, never bounce).
- Workspace motion lasts 160–240 ms with `cubic-bezier(.2,.8,.2,1)`. Showpiece motion is scroll-scrubbed.
- Numbers tween only on change and always land on the exact value.
- Reduced motion: every state change becomes an instant cross-fade.

**Key screen (home, 360 px).**
```
┌────────────────────────────────┐
│ Vaulta            ⌘K   🔔  ≡   │
├────────────────────────────────┤
│ Safe to spend today            │
│ ₹1,284                         │  ← Bricolage 72/opsz 96, tnum
│ of ₹21,830 left · 17 days      │
│ ────────────────────────────── │  ← the ledger rule
│ On pace for ₹34,200            │
│ ₹2,200 over budget   ▲         │  ← text + icon, not colour alone
│ ▕████████████████▏─────▏       │
├────────────────────────────────┤
│ Budgets                        │
│ Food & Dining   ₹4,850 / 6,000 │
│ ▕██████████████░░░░▏ 81%       │
├────────────────────────────────┤
│ Upcoming         Netflix  ₹649 │
│                  Tomorrow      │
└────────────────────────────────┘
```

---

## B. Monsoon Night

**Idea:** a dark-first cinematic world. Deep blue-black skies, a single saffron accent like a streetlight in rain. Money glows softly out of the dark.

**Palette.**
| Token | Dark | Light (secondary) |
|---|---|---|
| canvas | `#0A0F1C` | `#F3F4F8` |
| surface | `#121A2C` | `#FFFFFF` |
| ink | `#E7ECF7` | `#0F1526` |
| accent saffron | `#F0A43A` | `#9A5B00` |
| line | `#22304A` | `#D6DBE6` |

**Type pairing.** Schibsted Grotesk (display, condensed weights) with Geist and Geist Mono.

**Motion language:** "depth and light".
- Parallax layers, light sweeps across numbers, long eased fades (400–700 ms).
- Reduced motion drops parallax and sweeps.

**Key screen (landing hero).**
```
┌──────────────────────────────────────────────┐
│  night sky gradient, faint rain streaks       │
│                                               │
│   Every rupee, accounted for.                 │
│   ▸ Try the demo     Sign in with Google      │
│                                               │
│          ┌── glowing ₹1,284 ──┐               │
│          └────────────────────┘               │
└──────────────────────────────────────────────┘
```

**Why not.**
- Dark-first reads as "after-hours trading", not "my household money".
- Saffron glow on blue-black edges toward the crypto aesthetic the brief bans.
- The light theme would be an afterthought, while most finance checking happens in daylight on a phone.

---

## C. Paper Cut

**Idea:** layered paper. Statements, receipts and envelopes as tactile cut-paper planes that slide and fold. Cobalt ink on bone.

**Palette.** Bone `#F2F0EA`, cobalt `#2341C9`, ink `#141828`, with a dark variant of navy-black paper.

**Type pairing.** An editorial serif display (e.g. Tobias) with a grotesk UI.

**Motion language:** "fold and stack".
- Paper planes rotate in 3D, cards stack with physical shadows.
- Reduced motion uses flat cross-fades.

**Key screen (onboarding import).**
```
┌───────────────────────────────┐
│  [statement sheet, slight tilt]│
│   ~~~~ name ~~~~  ← folds away │
│   ~~~~ a/c no ~~  ← folds away │
│  [clean rows slide into an     │
│   envelope labelled Vaulta]    │
└───────────────────────────────┘
```

**Why not.**
- Skeuomorphic shadows and 3D folds cost frames on mid-range Android.
- It's hard to keep calm in a dense workspace: every card wants to be paper.
- Cobalt throws away the brand recognition the green already has.
- An editorial serif in data-dense UI hurts the legibility of money.

---

## Choice: A, Ledger

1. **Trust is the product.** The ledger is the oldest visual language of being accountable for money. Precision (alignment, tabular figures, rules) *is* the reassurance. It needs no glow to look expensive.
2. **One idea spans both modes.** The ruled line is cinematic on the landing page (a statement being dismantled row by row) and quiet in the workspace (rows, tracks, columns). Showpieces and workspace feel like one product.
3. **Both themes are first-class.** A cool paper/ink system inverts cleanly, and the green keeps its identity in both.
4. **Performance.** The motif is lines, type and transforms: no WebGL, no heavy shadows. 60 fps on mid-range Android is realistic, and the no-WebGL fallback is the design itself.
5. **Brand continuity.** Vaulta's green stays. Fraunces (an over-used display serif) is replaced by Bricolage Grotesque, which is more distinctive and fits the hand-set ledger feel.
