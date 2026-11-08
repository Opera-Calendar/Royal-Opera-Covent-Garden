# Royal Opera House — Opera & Ticket Sales calendar

Unofficial community-generated iCal subscriptions from public Royal Ballet and Opera pages.

- **Opera performances:** `royal-opera-house.ics`
- **General public ticket-sale starts:** `royal-opera-house-sales.ics`
- Uses London local time (Europe/London), including daylight-saving transitions.
- Sales are one-hour events with 90-day (approx. 3-month), 30-day (approx. 1-month), 7-day, 1-day VALARM reminders.
- Intended to follow future seasons: discovery is repeated daily, not hard-coded to 2026/27.
- **BETA / NEEDS LIVE VERIFICATION:** ROH does not publish a documented stable API for this approach. Some performance lists hide dates behind “Show all dates”. A workflow failure means calendars were **not** updated; check Actions logs. The implementation is best-effort and may require adjustment if the website changes. No guarantee of full coverage or sale lead time.
- If the website does not publish a sale date, it is not invented.
- Durations are approximate; if not parsed, a three-hour placeholder is used. Performances do not include reliable individual cast details (consult source URLs).

## Setup

1. Create a **public** GitHub repository.
2. Upload the contents of this ZIP, preserving `.github/workflows/update.yml`. On macOS Finder, hidden `.github` may be invisible: press `Cmd+Shift+.` to show hidden folders, or create workflow in the GitHub web editor.
3. In GitHub: **Settings → Actions → General → Workflow permissions**: select **Read and write permissions**, save.
4. Open **Actions → Update ROH opera calendars → Run workflow**.
5. Confirm that it turns **green** and the `.ics` files appear in repository root. **If red, do not subscribe yet**; inspect the log and fix the source parser.
6. Subscribe via **File → New Calendar Subscription** in Apple Calendar using:
   - `https://raw.githubusercontent.com/USERNAME/royal-opera-house-calendar/main/royal-opera-house.ics`
   - `https://raw.githubusercontent.com/USERNAME/royal-opera-house-calendar/main/royal-opera-house-sales.ics`
   Replace `USERNAME` with your GitHub username; if the default branch is not `main`, adjust accordingly.

## Sources

Official RBO listing: https://www.rbo.org.uk/tickets-and-events

Not affiliated with the Royal Ballet and Opera. Check official site before buying or travelling.
