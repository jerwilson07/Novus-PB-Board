# Novus PB Board

A standalone Discord Components V2 leaderboard bot, independent from Novus Role Sync, Novus Raider, and MEE6. The separate `index.html` remains a visual demo and is not connected to production Discord records.

## Discord experience

Run `/pbpanel` in the read-only `#pb-leaderboard` channel. The persistent public panel features:

- Four raid buttons, in order: **TFA (The Fractured Archive), ToB, CoX, ToA**, each with an optional custom emoji.
- Separate **Bosses**, **Submit PB**, and **PB Rules** actions.
- Per-raid mode/team-size selection, Top 5 ranking for that exact variant, prominent Novus #1, proof links, and Previous/Next navigation.
- Clean empty states, three recent approved PBs, and a relative "last approved" update time.
- An ephemeral browser for members, so only the main leaderboard message stays in the channel.

`/pbsubmit` opens the same submission modal as the Submit PB button. A date is mandatory (YYYY-MM-DD), as are the completion time and every participant. The PB must have been earned **while the submitter was in Novus**. For a group PB, every participant must have been a Novus member on the PB date. Discord member selection alone does *not* establish historical membership; staff must verify eligibility.

Proof can be added after submitting with `/pbproof`, using an image/video attachment or an HTTP(S) URL. Staff receives a private review card with **Approve**, **Deny**, and **Request Proof**, along with the existing approved #1 for the exact same category and variant. Approval requires proof, and staff must verify the date/participants before approving.

## Optional custom emojis

Add custom emojis to the Novus server (manually via Discord Server Settings) and use the emoji's complete Discord code (`<:emoji_name:id>` or `<a:emoji_name:id>`) in the following Railway variables:

- `PB_EMOJI_TFA`
- `PB_EMOJI_TOB`
- `PB_EMOJI_COX`
- `PB_EMOJI_TOA`

Default Unicode symbols appear if these are not configured. The bot must have access to each configured emoji.

## Railway setup

1. Create a distinct Discord application and bot named Novus PB. Invite it using the `bot` and `applications.commands` scopes. Grant View Channel, Send Messages, Read Message History, Embed Links and Use Application Commands.
2. Create the read-only `#pb-leaderboard` channel and a private `#pb-staff-review` channel accessible to the PB bot and staff.
3. Create a Railway service for this repo, start command `python bot.py`. Set `DISCORD_TOKEN`, `GUILD_ID`, and `REVIEW_CHANNEL_ID`. Add `STAFF_ROLE_IDS` if needed (Manage Server permissions also qualify).
4. **Mount a persistent Railway volume at /data** and set `DATABASE_PATH=/data/novus_pb.sqlite3`; otherwise records may be lost on redeployment.
5. Run `/pbpanel` in `#pb-leaderboard`, then pin the message. Existing panels automatically refresh on restart.

Never put the Discord token in GitHub or public messages.

## Animated PB banner

To use the animated logo in the existing `/pbpanel` Components V2 media gallery, upload the actual animated GIF to `assets/novus_pb_banner.gif` on the default GitHub branch (do not rename a PNG to GIF). The bot detects this asset on startup, uses its GitHub raw GIF URL, and edits the existing tracked PB home message in place when ready. The Raids, Bosses, and recent-PBs panels are not recreated. Railway must redeploy after the file upload. Until that asset exists, the current JPG stays in place. Alternatively set `PB_BANNER_URL` to a publicly accessible direct animated GIF URL in Railway.
