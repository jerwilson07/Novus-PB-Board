# Novus PB Board

A standalone Discord Components V2 bot. Independent from Novus Role Sync, Novus Raider and MEE6.

## Workflow

Create `#pb-leaderboard` as read-only for regular members, with history enabled; allow the PB bot to post and edit messages there. Create a private `#pb-staff-review` for staff and the PB bot.

Staff runs `/pbpanel` once in `#pb-leaderboard`. Members use the panel's Raids/Bosses buttons to browse current approved top-five times privately, with left/right activity navigation and each activity's variants stacked vertically.

`/pbsubmission` opens a private category and activity picker followed by a clean modal for time, players, and an optional proof URL. Staff receives a review card with **Approve**, **Deny**, and **Request Proof**. Approval requires proof; a member can attach evidence later using `/pbproof`.

The board uses a SQLite database. On Railway, **mount a persistent volume at /data** and use `DATABASE_PATH=/data/novus_pb.sqlite3`. Never store the bot token in GitHub.

## Railway setup

1. Create a distinct Discord application named Novus PB, invite it with `bot` and `applications.commands` scopes. Grant View Channel, Send Messages, Read Message History, Embed Links, and Use Application Commands. The separate staff channel must be visible to the bot.
2. Create a new Railway service pointing at this repository with start command `python bot.py`.
3. Set `DISCORD_TOKEN` to the **new** bot's secret token; `GUILD_ID` to the server ID; `REVIEW_CHANNEL_ID` to the private review channel ID; `DATABASE_PATH` to the persistent volume path. Set `STAFF_ROLE_IDS` to comma-separated staff role IDs if needed (Manage Server permissions also qualify).
4. In Discord, run `/pbpanel` inside `#pb-leaderboard`, then pin its message.

The existing `index.html` remains a visual demo, not a production data source.
