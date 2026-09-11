---
paths:
  - "assets/Scripts/UI/**"
---

# UI Code Rules

Scope: `assets/Scripts/UI/**` — screens, widgets, settings binders, and anything
that renders state to the player or turns a touch into an intent.

Sibling scope: `assets/Scripts/M1/**` is governed by
`.claude/rules/engine-code.md`, whose layering, engine-API, performance and
documentation rules apply here too. This file adds what is specific to UI.

**Case matters.** The Unity root in this repo is **lowercase `assets/`** — there
is no capital `Assets/` directory. Always write `assets/Scripts/UI/...`. See
`.claude/rules/case-sensitivity.md`.

Owning agent: `ui-programmer`.

## State

- **UI never owns or mutates game state.** It reads a snapshot and raises an
  intent; the sim decides. A UI class holding authoritative gameplay values is a
  defect.
- **No direct references from the sim to UI, ever.** Communication is one-way
  (`Assets/Scripts/UI/**` → `Greenwood.Sim`) plus sim-owned interfaces and events
  in the other direction.
- Persistence of UI preferences (volume, accessibility toggles) is handled by an
  explicit controller, not scattered across widgets.

## Platform — this is a touch-only portrait mobile game

Per `.claude/docs/technical-preferences.md` and
`design/ux/orientation-and-layout.md`:

- **Touch only. There is no gamepad and no keyboard.** Do not add gamepad
  navigation, focus rings, or key bindings — they are dead code here.
- **Single-thumb reachability, portrait-primary.** Interactive targets are
  ≥44 logical px.
- **Layout must survive live rotation to landscape** — portrait is primary but
  rotation is a runtime event, not a build variant. Test both.
- Pixel Perfect Camera settings are pinned in
  `docs/engine-reference/unity/VERSION.md`. No non-integer sprite scaling, no
  bilinear filtering, no anti-aliasing.

## Text and accessibility

- No hardcoded user-facing strings — all display text goes through the string
  table, with named placeholders for interpolated values.
- Scalable text and colourblind-safe encoding are mandatory, not optional. Never
  encode meaning in hue alone.
- All animations are skippable and respect the reduced-motion preference.
- Verify screens at the minimum and maximum supported resolutions, in both
  orientations.

## Audio

- UI sound goes through the AudioMixer buses (Field / Ledger / SFX / Music) via
  the audio event system — never by calling `AudioSource.Play` directly on a
  widget.
- **Never cross-fade between the Field and Ledger registers.** This is a
  forbidden pattern, listed in `.claude/docs/technical-preferences.md`.
- Volume is normalised `[0, 1]` at the API surface and converted to decibels at
  the mixer boundary, not before.

## Examples

**Correct** — normalised API, mixer at the boundary, no state ownership:

```csharp
/// <summary>Set Music bus volume. Value in [0, 1]; 0 = silence, 1 = full.</summary>
public void SetMusicVolume(float normalizedValue)
{
    float db = LinearToDb(normalizedValue);
    _musicDb = db;
    if (!_isMuted) _mixer.SetFloat(_musicParam, db);
}

/// <summary>Standard Unity AudioMixer linear-to-decibel mapping.</summary>
private static float LinearToDb(float normalizedValue)
    => Mathf.Log10(Mathf.Max(normalizedValue, 0.0001f)) * 20f;
```

**Incorrect** — four separate defects:

```csharp
public class BandPanel : MonoBehaviour
{
    public void OnRecruitPressed()
    {
        _band.Marks -= 40;                                  // VIOLATION: UI mutating game state
        _label.text = "Not enough marks";                   // VIOLATION: hardcoded user-facing string
        _statusDot.color = Color.red;                       // VIOLATION: meaning encoded in hue alone
        GetComponent<AudioSource>().Play();                 // VIOLATION: bypasses the mixer buses
    }
}
```
