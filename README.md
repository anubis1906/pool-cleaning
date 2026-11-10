# Pool Cleaning Reports (Home Assistant integration)

A custom [Home Assistant](https://www.home-assistant.io/) integration that
reads the weekly HTML service-report emails sent by a pool cleaning company
over IMAP and turns them into entities: chemical readings, chemicals added,
technician, visit time, a "safe to swim" time, and before/after photos.

It does not require anything from the pool company's side - it just logs
into your mailbox (or a dedicated forwarding mailbox) and reads the emails
that are already being sent there.

## How it works

1. On a schedule (default every 60 minutes, configurable), the integration
   logs into your mailbox over IMAP and searches for emails from the sender
   address you configured.
2. The newest unseen matching email is parsed. HA doesn't rely on exact
   markup - it walks the report's text in order and recognises the
   `POOL`/`SPA` section headers, the `CHEMICAL READINGS` and
   `CHEMICALS ADDED` tables, the job date/arrival/technician line, the
   customer address link, the "wait N hours" warning banner, and any
   before/after photos.
3. Home Assistant entities are created/updated from the parsed data. The
   integration remembers the last email UID it processed (in HA's storage)
   so it never reprocesses the same report.

## Installation

### HACS (recommended)

1. In HACS, add this repository as a custom repository (category:
   "Integration").
2. Install "Pool Cleaning Reports" and restart Home Assistant.

### Manual

Copy `custom_components/pool_cleaning` into your Home Assistant
`config/custom_components/` directory and restart Home Assistant.

## Setup

Settings → Devices & Services → Add Integration → "Pool Cleaning Reports".

You'll need:

- **IMAP server** and **port** (e.g. `imap.gmail.com`, `993`)
- **Username / password** - for Gmail, Outlook, Yahoo, iCloud, etc. you
  generally need an **app password** rather than your normal login
  password, since these providers block plain IMAP logins for regular
  passwords. A dedicated mailbox/alias that only receives the pool
  company's report emails (forwarded from your real inbox) also works well
  and keeps the scope of access minimal.
- **Sender address** (recommended) - restrict matching to emails from your
  pool company so nothing else in the inbox is parsed. Use the actual
  `From:` address, not a `Reply-To:` address - for example, PoolBrain-based
  report emails come from `notify@poolbrain.com`, even though replies go to
  the pool company's own address.

Afterwards, use the integration's "Configure" option to change the polling
interval or whether processed emails are marked as read.

## Entities created

A **Pool Service** device:

| Entity | Description |
| --- | --- |
| `sensor.pool_service_last_service` | Timestamp of the most recent visit (job date + arrival time). Attributes: customer name, address, warning text. |
| `sensor.pool_service_technician` | Name of the technician on the latest visit. |
| `sensor.pool_service_safe_to_swim_after` | Timestamp derived from the report's "wait N hours" warning, or unknown if none was given. |
| `binary_sensor.pool_service_wait_before_swimming` | On while a wait warning is in effect for the latest visit. |

One device per body of water reported on (e.g. **Pool**, **Spa**):

| Entity | Description |
| --- | --- |
| `sensor.<area>_chlorine`, `sensor.<area>_ph`, `sensor.<area>_salt`, ... | One sensor per chemical reading found in that area's "CHEMICAL READINGS" table. New reading types appear automatically the first time they show up in a report. |
| `sensor.<area>_chemicals_added` | Number of chemicals added during the latest visit; attributes list each chemical and amount (e.g. `Muriatic Acid: 32 fluid ounce`). |
| `image.<area>_before_photo` / `image.<area>_after_photo` | The latest before/after photo, if the report included one. |

## Service

`pool_cleaning.refresh` - checks the mailbox immediately instead of waiting
for the next scheduled poll.

## Tuning the parser for your provider

The parser in `custom_components/pool_cleaning/parser.py` was built against
a templated field-service report layout (job header, then a `POOL`/`SPA`
block with `CHEMICAL READINGS` and `CHEMICALS ADDED` tables). If your
provider's emails use a noticeably different layout and fields come back
empty, enable debug logging to see the raw parsed text and adjust the
regular expressions/section labels accordingly:

```yaml
logger:
  logs:
    custom_components.pool_cleaning: debug
```
