# Hockey Score

Live hockey scores, results and league standings on your Home Assistant dashboard.

Follow your team through the season: the live score while the game is on, the
latest result, the next game, and the full league table — plus events you can
use to celebrate every goal (yes, flashing lights).

## What you get

- **Score card** — live score with team logos, last result (WIN / LOSS / DRAW,
  extra time and shootouts marked), and the next game.
- **Standings card** — the full league table with your team highlighted.
- **Sensors** — always-fresh game data, badges and standings.
- **Events for automations** — a goal, game start and game end each fire
  exactly once, so a lost connection can never replay an old goal.

## What you need

- Home Assistant (2026.10 or newer)
- An **API URL** and an **API key**. Ask Victor!

## Install

1. In HACS, add this repository as a custom repository (category
   *Integration*) and install **Hockey Score**.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration** → **Hockey Score**,
   and enter the API URL and API key.

No HACS? Copy `custom_components/hockey_score/` into your own
`custom_components/` folder, then continue from step 2.

## Add the cards

Edit your dashboard → **Add card** → **Manual**, then paste:

Score card:

```yaml
type: custom:hockey-score-card
```

Standings card:

```yaml
type: custom:hockey-score-standings-card
```

Both find their sensors on their own. Cards are registered automatically when
the integration starts — no manual resource setup.

## The sensors

| Sensor | What it holds |
|---|---|
| `sensor.hockey_team` | Live/Idle and everything about the last, current and next game |
| `sensor.hockey_team_badges` | Team logos |
| `sensor.hockey_team_standings` | The league table |

## Events for your automations

| Event | Fires when | Useful fields |
|---|---|---|
| `hockey_score_goal` | your team scores | `team`, `opponent`, `home_score`, `away_score` |
| `hockey_score_game_start` | the game goes live | `team`, `opponent`, `period` |
| `hockey_score_game_end` | the game is finished | `team`, `opponent`, `team_result`, `team_score`, `opponent_score` |

All events fire only for your team. Example — a goal celebration that stays
quiet after 21:00:

```yaml
automation:
  - alias: Hockey goal!
    description: MÅL! — but never after bedtime.
    triggers:
      - trigger: event
        event_type: hockey_score_goal
    conditions:
      - condition: time
        before: "21:00:00"
    actions:
      - action: notify.notify
        data:
          title: "MÅL! 🏒"
          message: >
            {{ trigger.event.data.team }} {{ trigger.event.data.home_score }}
            - {{ trigger.event.data.away_score }} {{ trigger.event.data.opponent }}
```

## Credits

Built by a Leksands IF fan, for friends who bleed blue and white. LIF!
