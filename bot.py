import os, re, asyncio, logging
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse
import discord, aiosqlite
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
TOKEN=os.getenv("DISCORD_TOKEN","")
GUILD_ID=int(os.getenv("GUILD_ID","0"))
REVIEW_ID=int(os.getenv("REVIEW_CHANNEL_ID","0"))
DBPATH=os.getenv("DATABASE_PATH","novus_pb.sqlite3")
STAFF_ROLES={int(s) for s in os.getenv("STAFF_ROLE_IDS","").split(",") if s.strip().isdigit()}
GOLD=0xEAC17B
BLUE=0x57B7FF
RED=0xD94A4A
# Use the uploaded animation when present in the deployed repository.
# PB_BANNER_URL can override this with another public GIF URL.
PB_BANNER_GIF=Path(__file__).parent / "assets" / "novus_pb_banner.gif"
PB_BANNER_STATIC="https://raw.githubusercontent.com/jerwilson07/Novus-PB-Board/e56d115997dde7d1696ef4c535ce366da87ba84b/assets/novus_pb_banner.jpg"
PB_BANNER_ANIMATED="https://raw.githubusercontent.com/jerwilson07/Novus-PB-Board/main/assets/novus_pb_banner.gif"
PB_BANNER_URL=os.getenv("PB_BANNER_URL") or (PB_BANNER_ANIMATED if PB_BANNER_GIF.is_file() else PB_BANNER_STATIC)
RAIDS={
 "The Fractured Archive":["Solo","Duo","Trio","4-Man"],
 "Theatre of Blood":["Normal · Duo","Normal · Trio","Normal · 4-Man","Normal · 5-Man","Hard Mode · Trio","Hard Mode · 4-Man","Hard Mode · 5-Man"],
 "Chambers of Xeric":["Normal · Solo","Normal · Duo","Normal · Trio","Normal · 5-Man","Challenge Mode · Solo","Challenge Mode · Duo","Challenge Mode · Trio","Challenge Mode · 5-Man"],
 "Tombs of Amascut":["Expert · Solo","Expert · 8-Man"]}
RAID_LABELS={
 "The Fractured Archive":"TFA",
 "Theatre of Blood":"ToB",
 "Chambers of Xeric":"CoX",
 "Tombs of Amascut":"ToA",
}
BOSSES={
 "Inferno":["Standard"],
 "Fortis Colosseum":["Standard"],
 "Fight Caves":["Standard"],
 "Alchemical Hydra":["Standard"],
 "Araxxor":["Standard"],
 "Grotesque Guardians":["Standard"],
 "Gauntlet":["Standard"],
 "Corrupted Gauntlet":["Standard"],
 "Doom of Mokhaiotl":["Standard"],
 "Demonic Brutus":["Standard"],
 "Mad Angel":["Standard"],
 "Maggot King":["Standard"],
 "Phantom Muspah":["Standard"],
 "Phosani's Nightmare":["Standard"],
 "Royal Titans":["Standard"],
 "Vorkath":["Standard"],
 "Yama":["Standard"],
 "Zulrah":["Standard"],
 "Duke Sucellus":["Normal","Awakened"],
 "The Leviathan":["Normal","Awakened"],
 "Vardorvis":["Normal","Awakened"],
 "The Whisperer":["Normal","Awakened"]}
CATS={"Raids":RAIDS,"Bosses":BOSSES}
NON_SOLO_BOSSES={"Yama","Royal Titans"}

def solo_boss_variant(activity,variant):
 return activity not in NON_SOLO_BOSSES
MEDALS=["🥇","🥈","🥉","4.","5."]
PB_EARLIEST_DATE=datetime(2026,11,7).date()

def pb_date_eligible(value):
 return value>=PB_EARLIEST_DATE

def public_members(r):
 try: raw=r["member_ids"]
 except (KeyError,IndexError): raw=None
 ids=[x.strip() for x in (raw or "").split(",") if x.strip().isdigit()]
 return " · ".join(f"<@{x}>" for x in ids) if ids else clean(r["members"])

def unique_solo_results(results,limit=5):
 unique=[]
 seen=set()
 for r in results:
  raw_ids=r["member_ids"] or ""
  ids=[value.strip() for value in raw_ids.split(",") if value.strip().isdigit()]
  member_key=ids[0] if ids else clean(r["members"]).casefold()
  if member_key in seen:
   continue
  seen.add(member_key)
  unique.append(r)
  if len(unique)>=limit:
   break
 return unique

def unique_team_results(results,limit=5):
 unique=[]
 seen=set()
 for r in results:
  raw_ids=r["member_ids"] or ""
  ids=sorted(
   value.strip()
   for value in raw_ids.split(",")
   if value.strip().isdigit()
  )
  if ids:
   team_key=tuple(ids)
  else:
   team_key=tuple(
    sorted(
     name.strip().casefold()
     for name in str(r["members"]).split(",")
     if name.strip()
    )
   )
  if team_key in seen:
   continue
  seen.add(team_key)
  unique.append(r)
  if len(unique)>=limit:
   break
 return unique

def short_record(r,rank,include_variant=False):
 lines=[f"{MEDALS[rank]} **{fmt(r['ms'])}**"]
 if include_variant:
  lines.append(f"**{clean(r['variant'])}**")
 lines.append(public_members(r))
 if r["proof"] and valid_url(r["proof"]):
  lines.append(f"[↗ Proof]({r['proof']})")
 return "\n".join(lines)

def discord_updated(timestamp):
 if not timestamp:return None
 try:
  parsed=datetime.fromisoformat(timestamp.replace("Z","+00:00"))
  if parsed.tzinfo is None:
   parsed=parsed.replace(tzinfo=timezone.utc)
  return f"<t:{int(parsed.timestamp())}:R>"
 except (TypeError,ValueError,OverflowError):
  return None

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds")
# Server emoji names correspond to the PNG files in the Novus Discord emoji pack.
# No hardcoded emoji IDs: existing server emojis are resolved at render time.
ACTIVITY_EMOJIS={
 "The Fractured Archive":"tfa",
 "Theatre of Blood":"verzik",
 "Tombs of Amascut":"warden",
 "Chambers of Xeric":"COX",
 "Inferno":"zuk",
 "Fortis Colosseum":"sol_heredit",
 "Fight Caves":"jad",
 "Alchemical Hydra":"hydra",
 "Araxxor":"araxxor",
 "Grotesque Guardians":"dawn",
 "Gauntlet":"crystalline_hunllef",
 "Corrupted Gauntlet":"corrupted_hunllef",
 "Doom of Mokhaiotl":"doom",
 "Demonic Brutus":"demonic_brutus",
 "Mad Angel":"mad_angel",
 "Maggot King":"maggot_king",
 "Phantom Muspah":"muspah",
 "Phosani's Nightmare":"nightmare",
 "Royal Titans":"eldric",
 "Vorkath":"vorkath",
 "Yama":"yama",
 "Zulrah":"zulrah",
 "Duke Sucellus":"duke_sucellus",
 "The Leviathan":"leviathan",
 "Vardorvis":"vardorvis",
 "The Whisperer":"whisperer",
}

ACTIVITY_EMOJI_CACHE={}

async def fetch_activity_emojis(guild):
 try:
  server_emojis=await guild.fetch_emojis()
 except discord.HTTPException:
  logging.warning("Could not fetch server emojis for %s; using cache",guild.id)
  server_emojis=guild.emojis
 ACTIVITY_EMOJI_CACHE[guild.id]={
  emoji.name.casefold():str(emoji) for emoji in server_emojis
 }
 return ACTIVITY_EMOJI_CACHE[guild.id]

def activity_icon(activity):
 name=ACTIVITY_EMOJIS.get(activity)
 if not name:return ""
 guild=bot.get_guild(GUILD_ID) if GUILD_ID else (bot.guilds[0] if bot.guilds else None)
 if not guild:return ""
 resolved=ACTIVITY_EMOJI_CACHE.get(guild.id,{}).get(name.casefold())
 if not resolved:
  emoji=next((e for e in guild.emojis if e.name.casefold()==name.casefold()),None)
  resolved=str(emoji) if emoji else ""
 return f"{resolved} " if resolved else ""

def clean(v): return discord.utils.escape_mentions(discord.utils.escape_markdown(str(v)))
def valid_url(v):
 try:
  x=urlparse(v); return x.scheme in ("http","https") and bool(x.netloc)
 except ValueError: return False
def parse_ms(s):
 raw=s.strip()
 # Under one minute, seconds may be supplied without a 00: prefix.
 if re.fullmatch(r"\d{1,2}(?:\.\d{1,3})?",raw):
  parts=["0",raw]
 else:
  parts=raw.split(":")
 if len(parts) not in (2,3) or any(not x.isdecimal() for x in parts[:-1]):
  raise ValueError("Use SS.ss, MM:SS.ss, or HH:MM:SS.ss.")
 if not re.fullmatch(r"\d{1,2}(?:\.\d{1,3})?",parts[-1]):
  raise ValueError("Invalid seconds.")
 secs,*fraction=parts[-1].split(".")
 seconds=int(secs)
 ms=int(fraction[0].ljust(3,"0")) if fraction else 0
 minutes=int(parts[-2])
 hours=int(parts[0]) if len(parts)==3 else 0
 if seconds>59 or (len(parts)==3 and minutes>59):
  raise ValueError("Invalid seconds/minutes.")
 total=((hours*60+minutes)*60+seconds)*1000+ms
 if not 0<total<=86400000:
  raise ValueError("Time must be positive and within 24h.")
 return total
def fmt(ms):
 s,m=divmod(ms,1000); minute,sec=divmod(s,60); hour,minute=divmod(minute,60)
 cs=m//10
 return f"{hour}:{minute:02}:{sec:02}.{cs:02}" if hour else f"{minute}:{sec:02}.{cs:02}"

def proof_looks_like_media(url):
 try:
  path=urlparse(url).path.lower()
  return path.endswith((".png",".jpg",".jpeg",".gif",".webp",".mp4",".mov",".webm"))
 except ValueError:
  return False
def team_size(cat,variant,activity=None):
 if cat=="Bosses":
  return None if activity in NON_SOLO_BOSSES else 1
 if "Solo" in variant:return 1
 if "Duo" in variant:return 2
 if "Trio" in variant:return 3
 m=re.search(r"(\d+)-Man",variant);return int(m.group(1)) if m else None

def review_members(r):
 try: raw=r["member_ids"]
 except (KeyError,IndexError): raw=None
 ids=[x.strip() for x in (raw or "").split(",") if x.strip().isdigit()]
 return " · ".join(f"<@{x}>" for x in ids) if ids else clean(r["members"])

class Store:
 def __init__(self):self.conn=None;self.lock=asyncio.Lock()
 async def open(self):
  os.makedirs(os.path.dirname(os.path.abspath(DBPATH)),exist_ok=True)
  self.conn=await aiosqlite.connect(DBPATH)
  self.conn.row_factory=aiosqlite.Row
  await self.conn.execute("PRAGMA journal_mode=WAL")
  await self.conn.executescript("""CREATE TABLE IF NOT EXISTS submissions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,guild INTEGER NOT NULL,submitter INTEGER NOT NULL,
  category TEXT NOT NULL,activity TEXT NOT NULL,variant TEXT NOT NULL,
  members TEXT NOT NULL,member_ids TEXT,ms INTEGER NOT NULL,pb_date TEXT,proof TEXT,status TEXT NOT NULL DEFAULT 'pending',
  reviewer INTEGER,review_channel INTEGER,review_message INTEGER,created TEXT,updated TEXT);
  CREATE INDEX IF NOT EXISTS pb_rank ON submissions(guild,category,activity,variant,status,ms);
  CREATE TABLE IF NOT EXISTS panels(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);
  CREATE TABLE IF NOT EXISTS panel_banners(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);
  CREATE TABLE IF NOT EXISTS panel_bosses(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);
  CREATE TABLE IF NOT EXISTS boss_board_messages(guild INTEGER NOT NULL,activity TEXT NOT NULL,channel INTEGER NOT NULL,message INTEGER NOT NULL,PRIMARY KEY(guild,activity));
  CREATE TABLE IF NOT EXISTS panel_snapshot(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);
  CREATE TABLE IF NOT EXISTS panel_footer(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);""")
  async with self.conn.execute("PRAGMA table_info(submissions)") as c:
   columns={row[1] async for row in c}
  if "member_ids" not in columns:
   await self.conn.execute("ALTER TABLE submissions ADD COLUMN member_ids TEXT")
  if "pb_date" not in columns:
   await self.conn.execute("ALTER TABLE submissions ADD COLUMN pb_date TEXT")
  await self.conn.commit()
 async def one(self,q,args=()):
  async with self.conn.execute(q,args) as c:return await c.fetchone()
 async def all(self,q,args=()):
  async with self.conn.execute(q,args) as c:return await c.fetchall()
 async def add(self,g,u,cat,act,v,m,member_ids,ms,pb_date,p):
  async with self.lock:
   c=await self.conn.execute("""INSERT INTO submissions(guild,submitter,category,activity,variant,members,member_ids,ms,pb_date,proof,created,updated)
   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(g,u,cat,act,v,m,member_ids,ms,pb_date,p,now(),now()))
   await self.conn.commit();return c.lastrowid
 async def change(self,sid,prev,target,reviewer=None,proof=None):
  async with self.lock:
   if proof is None:
    c=await self.conn.execute("UPDATE submissions SET status=?,reviewer=?,updated=? WHERE id=? AND status=?",
      (target,reviewer,now(),sid,prev))
   else:
    c=await self.conn.execute("UPDATE submissions SET status=?,proof=?,updated=? WHERE id=? AND status=?",
      (target,proof,now(),sid,prev))
   await self.conn.commit();return c.rowcount==1
 async def attach_review(self,sid,ch,msg):
  async with self.lock:
   await self.conn.execute("UPDATE submissions SET review_channel=?,review_message=? WHERE id=?",(ch,msg,sid))
   await self.conn.commit()
 async def panel(self,g):return await self.one("SELECT * FROM panels WHERE guild=?",(g,))
 async def set_panel(self,g,ch,msg):
  async with self.lock:
   await self.conn.execute("""INSERT INTO panels VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE
   SET channel=excluded.channel,message=excluded.message""",(g,ch,msg))
   await self.conn.commit()
 async def banner(self,g):return await self.one("SELECT * FROM panel_banners WHERE guild=?",(g,))
 async def set_banner(self,g,ch,msg):
  async with self.lock:
   await self.conn.execute("""INSERT INTO panel_banners VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE
   SET channel=excluded.channel,message=excluded.message""",(g,ch,msg))
   await self.conn.commit()
 async def boss_panel(self,g):return await self.one("SELECT * FROM panel_bosses WHERE guild=?",(g,))
 async def set_boss_panel(self,g,ch,msg):
  async with self.lock:
   await self.conn.execute("""INSERT INTO panel_bosses VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE
   SET channel=excluded.channel,message=excluded.message""",(g,ch,msg))
   await self.conn.commit()
 async def boss_board(self,g,activity):
  return await self.one(
   "SELECT * FROM boss_board_messages WHERE guild=? AND activity=?",
   (g,activity)
  )
 async def boss_boards(self,g):
  return await self.all(
   "SELECT * FROM boss_board_messages WHERE guild=?",
   (g,)
  )
 async def set_boss_board(self,g,activity,ch,msg):
  async with self.lock:
   await self.conn.execute(
    """INSERT INTO boss_board_messages(guild,activity,channel,message)
    VALUES(?,?,?,?) ON CONFLICT(guild,activity) DO UPDATE SET
    channel=excluded.channel,message=excluded.message""",
    (g,activity,ch,msg)
   )
   await self.conn.commit()
 async def clear_boss_boards(self,g):
  async with self.lock:
   await self.conn.execute(
    "DELETE FROM boss_board_messages WHERE guild=?",
    (g,)
   )
   await self.conn.commit()
 async def snapshot_panel(self,g):return await self.one("SELECT * FROM panel_snapshot WHERE guild=?",(g,))
 async def set_snapshot_panel(self,g,ch,msg):
  async with self.lock:
   await self.conn.execute("""INSERT INTO panel_snapshot VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE
   SET channel=excluded.channel,message=excluded.message""",(g,ch,msg))
   await self.conn.commit()
 async def footer(self,g):return await self.one("SELECT * FROM panel_footer WHERE guild=?",(g,))
 async def set_footer(self,g,ch,msg):
  async with self.lock:
   await self.conn.execute("""INSERT INTO panel_footer VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE
   SET channel=excluded.channel,message=excluded.message""",(g,ch,msg))
   await self.conn.commit()
 async def ranking(self,g,cat,a,v):
  rows=await self.all("""SELECT * FROM submissions WHERE guild=? AND category=? AND activity=? AND variant=?
  AND status='approved' ORDER BY ms,id""",(g,cat,a,v))
  if cat=="Bosses" and solo_boss_variant(a,v):
   return unique_solo_results(rows,5)
  return unique_team_results(rows,5)
 async def best_approved(self,g,cat,activity,variant):
  return await self.one(
   """SELECT * FROM submissions
   WHERE guild=? AND category=? AND activity=? AND variant=?
   AND status='approved' ORDER BY ms,id LIMIT 1""",
   (g,cat,activity,variant)
  )
 async def recent_approved(self,g,limit=5):
  return await self.all("""SELECT * FROM submissions
  WHERE guild=? AND status='approved'
  ORDER BY updated DESC,id DESC LIMIT ?""",(g,limit))
 async def approved_for_points(self,g):
  return await self.all("""SELECT * FROM submissions
  WHERE guild=? AND status='approved'
  ORDER BY category,activity,variant,ms,id""",(g,))
 async def raid_top3(self,g,activity):
  rows=await self.all("""SELECT * FROM submissions
  WHERE guild=? AND category='Raids' AND activity=? AND status='approved'
  ORDER BY ms,id""",(g,activity))
  return unique_team_results(rows,3)
 async def clear_guild(self,g):
  async with self.lock:
   await self.conn.execute("DELETE FROM submissions WHERE guild=?",(g,))
   remaining=await self.one("SELECT COUNT(*) AS n FROM submissions")
   if remaining and remaining["n"]==0:
    await self.conn.execute("DELETE FROM sqlite_sequence WHERE name='submissions'")
   await self.conn.commit()
store=Store()
intents=discord.Intents.default()
class PB(commands.Bot):
 async def setup_hook(self):
  await store.open()
  self.add_view(Home())
  self.add_view(BossDirectory())
  for r in await store.all("SELECT * FROM submissions WHERE status IN ('pending','awaiting_proof') AND review_message IS NOT NULL"):
   self.add_view(await Review.make(r),message_id=r["review_message"])
  if GUILD_ID:
   guild=discord.Object(id=GUILD_ID)
   self.tree.copy_global_to(guild=guild)
   await self.tree.sync(guild=guild)
  else:await self.tree.sync()
bot=PB(command_prefix=commands.when_mentioned,intents=intents)

async def calculate_pb_points(g):
 rows=await store.approved_for_points(g)
 placement_points=(5,3,1)
 grouped={}
 scores={}

 for r in rows:
  key=(
   r["category"],
   r["activity"],
   r["variant"]
  )
  grouped.setdefault(key,[]).append(r)

 for key,results in grouped.items():
  category,activity,variant=key
  if category=="Bosses" and solo_boss_variant(activity,variant):
   results=unique_solo_results(results,5)
  else:
   results=unique_team_results(results,5)

  for rank,r in enumerate(results[:3]):
   raw_ids=r["member_ids"] or ""
   member_ids={
    int(value.strip())
    for value in raw_ids.split(",")
    if value.strip().isdigit()
   }

   for member_id in member_ids:
    entry=scores.setdefault(
     member_id,
     {
      "member_id":member_id,
      "points":0,
      "firsts":0,
      "seconds":0,
      "thirds":0,
     }
    )
    entry["points"]+=placement_points[rank]
    if rank==0:
     entry["firsts"]+=1
    elif rank==1:
     entry["seconds"]+=1
    else:
     entry["thirds"]+=1

 return sorted(
  scores.values(),
  key=lambda entry:(
   -entry["points"],
   -entry["firsts"],
   -entry["seconds"],
   -entry["thirds"],
   entry["member_id"],
  )
 )[:10]

async def paced_startup_edit(message, **kwargs):
 # Channel-wide edit bursts receive 429s. Leave headroom for other bots.
 await message.edit(**kwargs)
 await asyncio.sleep(1.4)

@bot.event
async def on_ready():
 # Refresh persisted views only once per process, not after every reconnect.
 if getattr(bot, "_startup_panels_refreshed", False):return
 bot._startup_panels_refreshed=True
 logging.info("Novus PB bot ready as %s (%s)",bot.user,bot.user.id)
 # Retrieve actual emoji IDs, then update existing leaderboard messages in place.
 for guild in bot.guilds:
  await fetch_activity_emojis(guild)
  records=await store.boss_boards(guild.id)
  jump_links={r["activity"]:f"https://discord.com/channels/{guild.id}/{r['channel']}/{r['message']}" for r in records}
  directory=await store.boss_panel(guild.id)
  if directory:
   try:
    ch=bot.get_channel(directory["channel"]) or await bot.fetch_channel(directory["channel"])
    message=await ch.fetch_message(directory["message"])
    await paced_startup_edit(view=BossDirectory(jump_links),allowed_mentions=discord.AllowedMentions.none())
   except discord.HTTPException:
    logging.exception("Failed to refresh PB directory emojis")
  # Update the existing home panel with the latest heading and points.
  home=await store.panel(guild.id)
  if home:
   try:
    ch=bot.get_channel(home["channel"]) or await bot.fetch_channel(home["channel"])
    message=await ch.fetch_message(home["message"])
    await paced_startup_edit(view=await Home.make(guild.id),allowed_mentions=discord.AllowedMentions.none())
   except discord.HTTPException:
    logging.exception("Failed to refresh PB home panel heading")
  # Refresh the existing footer in place so no /pbpanel rerun is needed.
  footer=await store.footer(guild.id)
  panel=await store.panel(guild.id)
  if footer and panel:
   try:
    ch=bot.get_channel(footer["channel"]) or await bot.fetch_channel(footer["channel"])
    message=await ch.fetch_message(footer["message"])
    url=f"https://discord.com/channels/{guild.id}/{panel['channel']}/{panel['message']}"
    await paced_startup_edit(content=f"## [↑ CLICK TO SCROLL TO THE TOP]({url})",allowed_mentions=discord.AllowedMentions.none())
   except discord.HTTPException:
    logging.exception("Failed to refresh PB scroll-to-top footer")
  for record in records:
   activity=record["activity"]
   if activity not in BOSSES and activity not in RAIDS:continue
   try:
    ch=bot.get_channel(record["channel"]) or await bot.fetch_channel(record["channel"])
    message=await ch.fetch_message(record["message"])
    view=await (BossLeaderboard.make(guild.id,activity) if activity in BOSSES else RaidLeaderboard.make(guild.id,activity))
    await paced_startup_edit(view=view,allowed_mentions=discord.AllowedMentions.none())
   except discord.HTTPException:
    logging.exception("Failed to refresh PB icon for %s",activity)

 # Update the tracked message in place after the animated asset deploys.
 # Do not delete/repost the board or alter its other panels.
 if PB_BANNER_URL != PB_BANNER_STATIC:
  for tracked in await store.all("SELECT guild,channel,message FROM panels"):
   try:
    channel=bot.get_channel(tracked["channel"]) or await bot.fetch_channel(tracked["channel"])
    message=await channel.fetch_message(tracked["message"])
    await paced_startup_edit(
     view=await Home.make(tracked["guild"]),
     allowed_mentions=discord.AllowedMentions.none()
    )
   except discord.HTTPException:
    logging.exception("Could not refresh PB banner in channel %s",tracked["channel"])

def is_staff(i):
 if not i.guild or not isinstance(i.user,discord.Member):return False
 m=i.user
 return m.guild_permissions.manage_guild or m.guild_permissions.administrator or bool(STAFF_ROLES.intersection(x.id for x in m.roles))

def is_council_or_founder(i):
 if not i.guild or not isinstance(i.user,discord.Member):return False
 allowed={"council","founder"}
 return any(role.name.casefold() in allowed for role in i.user.roles)

class RulesModal(ui.Modal,title="NOVUS | PB Rules"):
 def __init__(self):
  super().__init__(timeout=300)
  self.add_item(ui.TextDisplay(
   "**1. Novus-only records.** Your PB must have been achieved while you were "
   "a member of Novus. Older PBs are not eligible.\n\n"
   "**2. Group PBs.** Every player involved must have been a Novus member "
   "on the date of the run. List every participant accurately.\n\n"
   "**3. Record details.** Include the PB date, completion time, activity, "
   "mode/team size, and all involved players.\n\n"
   "**4. Proof.** Provide a dated screenshot, clip, or evidence URL. "
   "Use **/pbproof** after submitting if proof was not attached yet. "
   "Staff verifies eligibility and proof before approval.\n\n"
   "-# **Submit below only acknowledges these rules and closes this window. "
   "It does not submit a PB.**"
  ))

 async def on_submit(self,i):
  await i.response.defer(ephemeral=True)


class Home(ui.LayoutView):
 def __init__(self,points=None):
  super().__init__(timeout=None)
  points=points or []

  hero=ui.Container(accent_colour=GOLD)
  banner=ui.MediaGallery()
  banner.add_item(media=PB_BANNER_URL)
  hero.add_item(banner)
  hero.add_item(ui.TextDisplay(
   "## ✦ NOVUS · PERSONAL BESTS"
  ))
  hero.add_item(ui.Separator())

  points_lines=[
   "### TOP 10",
   "-# 1st = 5 pts · 2nd = 3 pts · 3rd = 1 pt",
  ]

  if not points:
   points_lines.append("-# No approved PB points yet.")
  else:
   for index,entry in enumerate(points,1):
    rank_display={1:"🏆",2:"🥈",3:"🥉"}.get(index,f"**{index}.**")
    points_lines.append(
     f"{rank_display} <@{entry['member_id']}> · "
     f"**{entry['points']} pts** "
     f"- ({entry['firsts']} first · {entry['seconds']} second · {entry['thirds']} third)"
    )

  hero.add_item(
   ui.TextDisplay("\n".join(points_lines))
  )
  hero.add_item(ui.Separator())

  actions=ui.ActionRow()
  submit=ui.Button(
   label="Submit PB",
   style=discord.ButtonStyle.success,
   custom_id="pb:home:submit"
  )
  rules=ui.Button(
   label="PB Rules",
   style=discord.ButtonStyle.danger,
   custom_id="pb:home:rules"
  )
  async def open_submit(i):
   await i.response.send_modal(SubmitModal())
  async def open_rules(i):
   await i.response.send_modal(RulesModal())
  submit.callback=open_submit
  rules.callback=open_rules
  actions.add_item(submit)
  actions.add_item(rules)
  hero.add_item(actions)

  self.add_item(hero)

 @classmethod
 async def make(cls,g):
  return cls(await calculate_pb_points(g))


class SnapshotPanel(ui.LayoutView):
 def __init__(self,raid_leaders=None,recent=None):
  super().__init__(timeout=None)
  raid_leaders=raid_leaders or {}
  recent=recent or []

  records=ui.Container(accent_colour=BLUE)
  snapshot=["### RAID SNAPSHOT"]
  for activity in RAIDS:
   results=raid_leaders.get(activity,[])
   snapshot.append(f"\n{activity_icon(activity)}**{clean(activity)}**")
   if results:
    snapshot.extend(short_record(r,k,include_variant=True) for k,r in enumerate(results))
   else:
    snapshot.append("-# No records yet.")
  records.add_item(ui.TextDisplay("\n".join(snapshot)))

  recent_panel=ui.Container(accent_colour=BLUE)
  updated=discord_updated(recent[0]["updated"]) if recent else None
  recent_panel.add_item(ui.TextDisplay(
   "### RECENT PBs"
   + (f"\n-# UPDATED {updated}" if updated else "")
  ))
  if not recent:
   recent_panel.add_item(ui.TextDisplay(
    "-# No recent PBs."
   ))
  else:
   for idx,r in enumerate(recent):
    activity=RAID_LABELS.get(r["activity"],r["activity"])
    recent_text=(
     f"**{clean(activity)} · {clean(r['variant'])}**\n"
     f"**{fmt(r['ms'])}**\n"
     f"{public_members(r)}"
    )
    if r["proof"] and valid_url(r["proof"]):
     recent_text+=f"\n[↗ Proof]({r['proof']})"
    recent_panel.add_item(ui.TextDisplay(recent_text))
    if idx!=len(recent)-1:
     recent_panel.add_item(ui.Separator())

  self.add_item(records)
  self.add_item(recent_panel)

 @classmethod
 async def make(cls,g):
  leaders={
   activity:await store.raid_top3(g,activity)
   for activity in RAIDS
  }
  return cls(
   leaders,
   await store.recent_approved(g,3)
  )


class BossDirectory(ui.LayoutView):
 def __init__(self,jump_links=None):
  super().__init__(timeout=None)
  jump_links=jump_links or {}

  panel=ui.Container(accent_colour=BLUE)
  panel.add_item(ui.TextDisplay(
   "## Boss Directory\n"
   "-# Select an activity to jump to its leaderboard."
  ))

  lines=[
   "### Minigames",
  ]

  for name in ("Inferno","Fortis Colosseum","Fight Caves"):
   url=jump_links.get(name)
   lines.append(
    f"{activity_icon(name)}[{name}]({url})"
    if url
    else f"{activity_icon(name)}**{name}**"
   )

  lines.append("### Raids")
  for activity in RAIDS:
   label=RAID_LABELS[activity]
   url=jump_links.get(activity)
   lines.append(
    f"{activity_icon(activity)}[{label}]({url})"
    if url
    else f"{activity_icon(activity)}**{label}**"
   )

  remaining_groups=[
   ("Slayer Bosses",[
    "Alchemical Hydra","Araxxor","Grotesque Guardians"
   ]),
   ("Solo & Duo Bosses",[
    "Gauntlet","Corrupted Gauntlet","Doom of Mokhaiotl","Demonic Brutus",
    "Mad Angel","Maggot King","Phantom Muspah","Phosani's Nightmare",
    "Royal Titans","Vorkath","Yama","Zulrah"
   ]),
   ("DT2 Bosses",[
    "Duke Sucellus","The Leviathan","Vardorvis","The Whisperer"
   ])
  ]

  for heading,names in remaining_groups:
   lines.append(f"### {heading}")
   for name in names:
    url=jump_links.get(name)
    lines.append(
     f"{activity_icon(name)}[{name}]({url})"
     if url
     else f"{activity_icon(name)}**{name}**"
    )

  panel.add_item(
   ui.TextDisplay("\n".join(lines))
  )
  self.add_item(panel)


class BossLeaderboard(ui.LayoutView):
 def __init__(self,activity,blocks):
  super().__init__(timeout=None)

  accent=RED if activity in ("Inferno","Fortis Colosseum","Fight Caves") else BLUE
  panel=ui.Container(accent_colour=accent)
  panel.add_item(ui.TextDisplay(
   f"## {activity_icon(activity)}{clean(activity)}"
  ))

  for block_index,(variant,results) in enumerate(blocks):
   if block_index:
    panel.add_item(ui.Separator())

   lines=[]
   if len(blocks)>1:
    lines.append(f"### {clean(variant)}")

   for rank in range(5):
    medal=MEDALS[rank]
    if rank < len(results):
     r=results[rank]
     proof=(
      f" · [Proof]({r['proof']})"
      if r["proof"] and valid_url(r["proof"])
      else ""
     )
     lines.append(
      f"{medal} **{fmt(r['ms'])}**{proof} · {public_members(r)}"
     )
    else:
     lines.append(
      f"{medal} Empty"
     )

   panel.add_item(
    ui.TextDisplay("\n".join(lines))
   )

  self.add_item(panel)

 @classmethod
 async def make(cls,g,activity):
  return cls(
   activity,
   [
    (
     variant,
     await store.ranking(
      g,
      "Bosses",
      activity,
      variant
     )
    )
    for variant in BOSSES[activity]
   ]
  )


class RaidLeaderboard(ui.LayoutView):
 def __init__(self,activity,blocks):
  super().__init__(timeout=None)

  panel=ui.Container(accent_colour=GOLD)
  panel.add_item(ui.TextDisplay(
   f"## {activity_icon(activity)}{clean(activity)}"
  ))

  for block_index,(variant,results) in enumerate(blocks):
   if block_index:
    panel.add_item(ui.Separator())

   lines=[f"### {clean(variant)}"]

   for rank in range(5):
    medal=MEDALS[rank]
    if rank < len(results):
     r=results[rank]
     proof=(
      f" · [Proof]({r['proof']})"
      if r["proof"] and valid_url(r["proof"])
      else ""
     )
     lines.append(
      f"{medal} **{fmt(r['ms'])}**{proof} · {public_members(r)}"
     )
    else:
     lines.append(
      f"{medal} Empty"
     )

   panel.add_item(
    ui.TextDisplay("\n".join(lines))
   )

  self.add_item(panel)

 @classmethod
 async def make(cls,g,activity):
  return cls(
   activity,
   [
    (
     variant,
     await store.ranking(
      g,
      "Raids",
      activity,
      variant
     )
    )
    for variant in RAIDS[activity]
   ]
  )


class RaidBrowser(ui.LayoutView):
 def __init__(self,g,raid_index,variant_index,results):
  super().__init__(timeout=900)
  self.g=g
  self.raid_index=raid_index
  self.variant_index=variant_index

  activities=list(RAIDS)
  activity=activities[raid_index]
  variants=RAIDS[activity]
  variant=variants[variant_index]

  panel=ui.Container(accent_colour=GOLD)
  panel.add_item(ui.TextDisplay(
   f"## ✦ NOVUS · {activity_icon(activity)}{clean(activity)}"
  ))

  raid_row=ui.ActionRow()
  for idx,name in enumerate(activities):
   button=ui.Button(
    label=("✓ " if idx==raid_index else "")+RAID_LABELS[name],
    style=(
     discord.ButtonStyle.primary if idx==raid_index
     else discord.ButtonStyle.secondary
    )
   )
   async def switch_raid(i,target=idx):
    await i.response.edit_message(
     view=await RaidBrowser.make(self.g,target,0)
    )
   button.callback=switch_raid
   raid_row.add_item(button)
  panel.add_item(raid_row)

  panel.add_item(ui.Separator())
  variant_select=ui.Select(
   placeholder="Filter by mode / team size",
   min_values=1,
   max_values=1,
   options=[
    discord.SelectOption(
     label=name,
     value=str(idx),
     default=idx==variant_index
    )
    for idx,name in enumerate(variants)
   ]
  )
  async def choose_variant(i):
   target=int(variant_select.values[0])
   await i.response.edit_message(
    view=await RaidBrowser.make(self.g,self.raid_index,target)
   )
  variant_select.callback=choose_variant
  variant_row=ui.ActionRow()
  variant_row.add_item(variant_select)
  panel.add_item(variant_row)

  rankings=ui.Container(accent_colour=BLUE)
  rankings.add_item(ui.TextDisplay(
   f"### {clean(variant)} · TOP 5"
  ))
  rankings.add_item(ui.Separator())

  if not results:
   rankings.add_item(ui.TextDisplay(
    "-# No records yet."
   ))
  else:
   champion=results[0]
   top_text=(
    f"## 🥇 {fmt(champion['ms'])}\n"
    f"{public_members(champion)}"
   )
   if champion["proof"] and valid_url(champion["proof"]):
    top_text+=f"\n[↗ Proof]({champion['proof']})"
   rankings.add_item(ui.Section(
    ui.TextDisplay(top_text),
    accessory=ui.Button(
     label="NOVUS #1",
     style=discord.ButtonStyle.secondary,
     disabled=True
    )
   ))
   if len(results)>1:
    rankings.add_item(ui.Separator())
    rankings.add_item(ui.TextDisplay(
     "\n".join(short_record(r,k) for k,r in enumerate(results) if k>0)
    ))

  shortcuts=ui.ActionRow()
  submit=ui.Button(label="Submit PB",style=discord.ButtonStyle.success)
  rules=ui.Button(label="PB Rules",style=discord.ButtonStyle.danger)
  bosses=ui.Button(label="Bosses",style=discord.ButtonStyle.secondary)

  async def open_submit(i):
   await i.response.send_modal(SubmitModal())
  async def open_rules(i):
   await i.response.send_modal(RulesModal())
  async def open_bosses(i):
   await i.response.edit_message(view=await Browser.make(self.g,"Bosses",0))

  submit.callback=open_submit
  rules.callback=open_rules
  bosses.callback=open_bosses
  shortcuts.add_item(submit)
  shortcuts.add_item(rules)
  shortcuts.add_item(bosses)
  rankings.add_item(shortcuts)

  self.add_item(panel)
  self.add_item(rankings)

 @classmethod
 async def make(cls,g,raid_index,variant_index):
  activities=list(RAIDS)
  raid_index%=len(activities)
  activity=activities[raid_index]
  variants=RAIDS[activity]
  variant_index%=len(variants)
  variant=variants[variant_index]
  results=await store.ranking(g,"Raids",activity,variants[variant_index])
  return cls(g,raid_index,variant_index,results)


class Browser(ui.LayoutView):
 def __init__(self,g,cat,index,blocks):
  super().__init__(timeout=900)
  self.g=g
  self.cat=cat
  self.index=index
  activities=CATS[cat]
  name=list(activities)[index]

  panel=ui.Container(accent_colour=GOLD)
  panel.add_item(ui.TextDisplay(
   f"## ✦ NOVUS · {clean(name)}"
  ))

  tabs=ui.ActionRow()
  raids=ui.Button(label="Raids",style=discord.ButtonStyle.secondary)
  bosses=ui.Button(label="Bosses",style=discord.ButtonStyle.primary)
  async def show_raids(i):
   await i.response.edit_message(view=await RaidBrowser.make(self.g,0,0))
  async def show_bosses(i):
   await i.response.edit_message(view=await Browser.make(self.g,"Bosses",0))
  raids.callback=show_raids
  bosses.callback=show_bosses
  tabs.add_item(raids)
  tabs.add_item(bosses)
  panel.add_item(tabs)
  panel.add_item(ui.Separator())

  rankings=ui.Container(accent_colour=BLUE)
  for pos,(variant,results) in enumerate(blocks):
   if pos:
    rankings.add_item(ui.Separator())
   lines=[f"### {clean(variant)} · TOP 5"]
   if not results:
    lines.append("-# No records yet.")
   else:
    for rank,r in enumerate(results):
     if rank:
      lines.append("")
     lines.append(short_record(r,rank))
   rankings.add_item(ui.TextDisplay("\n".join(lines)))

  shortcuts=ui.ActionRow()
  submit=ui.Button(label="Submit PB",style=discord.ButtonStyle.success)
  rules=ui.Button(label="PB Rules",style=discord.ButtonStyle.danger)
  async def open_submit(i):
   await i.response.send_modal(SubmitModal())
  async def open_rules(i):
   await i.response.send_modal(RulesModal())
  submit.callback=open_submit
  rules.callback=open_rules
  shortcuts.add_item(submit)
  shortcuts.add_item(rules)
  rankings.add_item(shortcuts)

  self.add_item(panel)
  self.add_item(rankings)

 @classmethod
 async def make(cls,g,cat,index):
  names=list(CATS[cat])
  index%=len(names)
  activity=names[index]
  return cls(
   g,cat,index,[
    (variant,await store.ranking(g,cat,activity,variant))
    for variant in CATS[cat][activity]
   ]
  )


class Review(ui.LayoutView):
 def __init__(self,r,leader=None,placement=None):
  active=r["status"] in ("pending","awaiting_proof")
  super().__init__(timeout=None if active else 60)
  self.sid=r["id"]
  status=r["status"].replace("_"," ").title()
  status_style={
   "pending":discord.ButtonStyle.secondary,
   "awaiting_proof":discord.ButtonStyle.primary,
   "approved":discord.ButtonStyle.success,
   "denied":discord.ButtonStyle.danger,
  }.get(r["status"],discord.ButtonStyle.secondary)

  panel=ui.Container(accent_colour=GOLD)
  status_badge=ui.Button(
   label=status,
   style=status_style,
   disabled=True,
   custom_id=f"pb:status:{self.sid}"
  )
  panel.add_item(
   ui.Section(
    ui.TextDisplay(
     f"## ✦ NOVUS | PB REVIEW\n"
     f"**{clean(r['activity'])}** · {clean(r['variant'])}\n"
     f"-# Submission #{r['id']} · Submitted by <@{r['submitter']}>"
    ),
    accessory=status_badge
   )
  )

  panel.add_item(ui.Separator())
  panel.add_item(ui.TextDisplay("-# PB DATE\n" f"**{clean(r['pb_date'] or 'Not recorded')}**"))
  if active:
   panel.add_item(ui.TextDisplay(
    "-# CURRENT #1\n" +
    (f"**{review_members(leader)}** · **{fmt(leader['ms'])}**" if leader else "No approved record yet.")
   ))
   panel.add_item(ui.Separator())
   if not leader:
    difference="First record for this leaderboard"
   elif r["ms"]<leader["ms"]:
    difference=f"{fmt(leader['ms']-r['ms'])} faster than current #1"
   elif r["ms"]>leader["ms"]:
    difference=f"{fmt(r['ms']-leader['ms'])} behind current #1"
   else:
    difference="Tied with current #1"
   label=(f"NEW #{placement}" if isinstance(placement,int) else
          "NO RANK CHANGE" if placement=="unchanged" else "OUTSIDE TOP 5")
   panel.add_item(ui.Section(
    ui.TextDisplay("-# SUBMITTED PB\n"
     f"**{review_members(r)}** · **{fmt(r['ms'])}**\n"
     f"-# {difference}"),
    accessory=ui.Button(label=label,disabled=True,
     style=discord.ButtonStyle.success if placement==1 else discord.ButtonStyle.secondary,
     custom_id=f"pb:placement:{self.sid}")
   ))

  p=r["proof"]
  if p and valid_url(p):
   panel.add_item(
    ui.TextDisplay(
     "### Proof\n"
     f"[Open submitted evidence]({p})"
    )
   )
   if proof_looks_like_media(p):
    gallery=ui.MediaGallery()
    gallery.add_item(media=p,description="Submitted PB proof")
    panel.add_item(gallery)
  else:
   panel.add_item(
    ui.TextDisplay(
     "### PROOF\n"
     "-# Awaiting proof."
    )
   )

  if active:
   panel.add_item(ui.Separator())
   decision_row=ui.ActionRow()
   approve=ui.Button(
    label="Approve",
    style=discord.ButtonStyle.success,
    custom_id=f"pb:review:approve:{self.sid}"
   )
   deny=ui.Button(
    label="Deny",
    style=discord.ButtonStyle.danger,
    custom_id=f"pb:review:deny:{self.sid}"
   )
   async def approve_clicked(i):await decide(i,self.sid,"approve")
   async def deny_clicked(i):await decide(i,self.sid,"deny")
   approve.callback=approve_clicked
   deny.callback=deny_clicked
   request=ui.Button(
    label="Request Proof",
    style=discord.ButtonStyle.primary,
    custom_id=f"pb:review:request:{self.sid}"
   )
   async def request_clicked(i):await decide(i,self.sid,"request")
   request.callback=request_clicked
   decision_row.add_item(approve)
   decision_row.add_item(deny)
   decision_row.add_item(request)
   panel.add_item(decision_row)

  self.add_item(panel)

 @classmethod
 async def make(cls,r):
  leader=None
  placement=None
  if r["status"] in ("pending","awaiting_proof"):
   rows=await store.all(
    """SELECT * FROM submissions WHERE guild=? AND category=? AND activity=? AND variant=?
    AND status='approved' ORDER BY ms,id""",
    (r["guild"],r["category"],r["activity"],r["variant"])
   )
   leader=rows[0] if rows else None
   candidates=sorted([*rows,r],key=lambda entry:(entry["ms"],entry["id"]))
   unique_fn=(unique_solo_results if r["category"]=="Bosses"
              and solo_boss_variant(r["activity"],r["variant"]) else unique_team_results)
   projected=unique_fn(candidates,5)
   placement=next((i for i,item in enumerate(projected,1) if item["id"]==r["id"]),None)
   if placement is None:
    all_unique=unique_fn(candidates,len(candidates))
    placement="unchanged" if not any(item["id"]==r["id"] for item in all_unique) else "outside"
  return cls(r,leader,placement)


async def refresh_panel(g,activity=None):
 home=await store.panel(g)
 if home:
  try:
   ch=bot.get_channel(home["channel"]) or await bot.fetch_channel(home["channel"])
   msg=await ch.fetch_message(home["message"])
   await msg.edit(
    view=await Home.make(g),
    allowed_mentions=discord.AllowedMentions.none()
   )
  except discord.HTTPException:
   logging.exception("Unable to refresh PB points panel")

 r=await store.snapshot_panel(g)
 if r:
  try:
   ch=bot.get_channel(r["channel"]) or await bot.fetch_channel(r["channel"])
   msg=await ch.fetch_message(r["message"])
   await msg.edit(
    view=await SnapshotPanel.make(g),
    allowed_mentions=discord.AllowedMentions.none()
   )
  except discord.HTTPException:
   logging.exception("Unable to refresh public panel")

 if activity in BOSSES:
  public_activities=[("Bosses",activity)]
 elif activity in RAIDS:
  public_activities=[("Raids",activity)]
 else:
  public_activities=(
   [("Bosses",name) for name in BOSSES]
   + [("Raids",name) for name in RAIDS]
  )

 for category,name in public_activities:
  tracked=await store.boss_board(g,name)
  if not tracked:
   continue
  try:
   ch=bot.get_channel(tracked["channel"]) or await bot.fetch_channel(tracked["channel"])
   msg=await ch.fetch_message(tracked["message"])
   view=(
    await BossLeaderboard.make(g,name)
    if category=="Bosses"
    else await RaidLeaderboard.make(g,name)
   )
   await msg.edit(
    view=view,
    allowed_mentions=discord.AllowedMentions.none()
   )
  except discord.HTTPException:
   logging.exception(
    "Unable to refresh public PB board for %s",
    name
   )


async def update_review(r):
 if not r["review_message"]:return
 try:
  ch=bot.get_channel(r["review_channel"]) or await bot.fetch_channel(r["review_channel"])
  msg=await ch.fetch_message(r["review_message"])
  await msg.edit(view=await Review.make(r))
 except discord.HTTPException:logging.exception("Unable to update review")

async def decide(i,sid,choice):
 if not is_staff(i):return await i.response.send_message("Staff only.",ephemeral=True)
 r=await store.one("SELECT * FROM submissions WHERE id=?",(sid,))
 if not r or r["guild"]!=i.guild_id:return await i.response.send_message("Record not found.",ephemeral=True)
 if r["status"] not in ("pending","awaiting_proof"):return await i.response.send_message("Already resolved.",ephemeral=True)
 if choice=="approve" and not r["proof"]:
  return await i.response.send_message("Proof is required. Use Request Proof.",ephemeral=True)
 if choice=="request" and r["status"]=="awaiting_proof":
  return await i.response.send_message("Already awaiting proof.",ephemeral=True)
 target={"approve":"approved","deny":"denied","request":"awaiting_proof"}[choice]
 if not await store.change(sid,r["status"],target,i.user.id):
  return await i.response.send_message("Another reviewer updated this record.",ephemeral=True)
 updated=await store.one("SELECT * FROM submissions WHERE id=?",(sid,))
 await i.response.edit_message(view=await Review.make(updated))
 if choice=="approve":await refresh_panel(i.guild_id,updated["activity"])
 if choice=="request":
  try:
   user=await bot.fetch_user(r["submitter"])
   await user.send(f"Your Novus PB #{sid} needs proof. Use /pbproof with submission_id {sid} in the Novus server.")
  except discord.HTTPException:logging.warning("Unable to DM submission owner")

class ProofUploadModal(ui.Modal,title="NOVUS | PB Proof"):
 def __init__(self,sid):
  super().__init__(timeout=300)
  self.sid=sid
  self.proof_upload=ui.FileUpload(
   custom_id="pb:proof:upload",
   required=True,
   min_values=1,
   max_values=1
  )
  self.add_item(ui.Label(
   text="Proof",
   description="Upload a screenshot or video clip of the PB.",
   component=self.proof_upload
  ))

 async def on_submit(self,i):
  r=await store.one(
   "SELECT * FROM submissions WHERE id=? AND guild=?",
   (self.sid,i.guild_id)
  )
  if not r or (r["submitter"]!=i.user.id and not is_staff(i)):
   return await i.response.send_message("PB not found or not yours.",ephemeral=True)
  if r["status"] not in ("pending","awaiting_proof"):
   return await i.response.send_message("PB is already resolved.",ephemeral=True)

  attachment=self.proof_upload.values[0]
  if not (attachment.content_type or "").startswith(("image/","video/")):
   return await i.response.send_message("Only image/video files accepted.",ephemeral=True)

  proof=attachment.url
  if not valid_url(proof):
   return await i.response.send_message("Discord did not return a valid proof attachment URL.",ephemeral=True)

  await i.response.defer(ephemeral=True)
  if not await store.change(self.sid,r["status"],"pending",proof=proof):
   return await i.followup.send("Submission changed; retry.",ephemeral=True)
  updated=await store.one("SELECT * FROM submissions WHERE id=?",(self.sid,))
  await update_review(updated)
  await i.followup.send(
   f"Proof saved for PB #{self.sid}. Staff can review it now.",
   ephemeral=True
  )


class ProofUploadView(ui.View):
 def __init__(self,sid):
  super().__init__(timeout=900)
  self.sid=sid
  attach=ui.Button(
   label="Attach Proof",
   style=discord.ButtonStyle.primary,
   custom_id=f"pb:proof:button:{sid}"
  )
  async def attach_clicked(i):
   await i.response.send_modal(ProofUploadModal(self.sid))
  attach.callback=attach_clicked
  self.add_item(attach)


async def submit(i,cat,act,variant,t,pb_date,members,proof=""):
 try:ms=parse_ms(t)
 except ValueError as e:return await i.response.send_message(str(e),ephemeral=True)

 raw_date=pb_date.strip()
 parsed_date=None
 for date_format in ("%m-%d-%Y","%Y-%m-%d","%m/%d/%Y"):
  try:
   parsed_date=datetime.strptime(raw_date,date_format).date()
   break
  except ValueError:
   pass
 if parsed_date is None:
  return await i.response.send_message(
   "Enter the PB date as MM/DD/YYYY or MM-DD-YYYY.",
   ephemeral=True
  )
 if not pb_date_eligible(parsed_date):
  return await i.response.send_message(
   "Only PBs achieved on or after **November 7, 2026** are eligible.",
   ephemeral=True
  )
 if parsed_date>datetime.now(timezone.utc).date():
  return await i.response.send_message(
   "The PB date cannot be in the future.",
   ephemeral=True
  )
 normalized_date=parsed_date.isoformat()

 required=team_size(cat,variant,act)
 if not members:
  return await i.response.send_message("Select at least one party member.",ephemeral=True)
 if cat=="Bosses" and act in NON_SOLO_BOSSES and len(members) not in (1,2):
  return await i.response.send_message("Expected 1 or 2 Discord member(s) for this boss.",ephemeral=True)
 if required is not None and len(members)!=required:
  return await i.response.send_message(f"Expected {required} Discord member(s) for this category.",ephemeral=True)
 if len({m.id for m in members})!=len(members):
  return await i.response.send_message("Each party member can only be selected once.",ephemeral=True)
 if proof and not valid_url(proof):
  return await i.response.send_message("Provide an HTTP(S) proof link, or add proof later with /pbproof.",ephemeral=True)

 try:ch=bot.get_channel(REVIEW_ID) or await bot.fetch_channel(REVIEW_ID)
 except discord.HTTPException:return await i.response.send_message("Staff review channel not available.",ephemeral=True)

 await i.response.defer(thinking=True,ephemeral=True)
 names=", ".join(m.display_name for m in members)
 member_ids=",".join(str(m.id) for m in members)
 sid=await store.add(i.guild_id,i.user.id,cat,act,variant,names,member_ids,ms,normalized_date,proof)
 r=await store.one("SELECT * FROM submissions WHERE id=?",(sid,))
 try:
  message=await ch.send(view=await Review.make(r),allowed_mentions=discord.AllowedMentions.none())
  await store.attach_review(sid,ch.id,message.id)
 except discord.HTTPException:
  logging.exception("Staff review message failed")
  return await i.followup.send(f"Submission #{sid} saved, but staff delivery failed. Notify staff.",ephemeral=True)
 await i.followup.send(
  f"PB #{sid} submitted for staff review for **{normalized_date}**. "
  "The PB must have been achieved after you joined Novus; for group PBs, every listed player "
  "must also have been a Novus member on that date. "
  + ("Proof received." if proof else "Attach proof below, or use /pbproof later."),
  ephemeral=True,
  view=None if proof else ProofUploadView(sid)
 )

def submission_target_options():
 options=[
  discord.SelectOption(
   label=activity,
   value=f"raid|||{activity}"
  )
  for activity in RAIDS
 ]
 options.append(
  discord.SelectOption(
   label="Boss PB",
   value="boss"
  )
 )
 return options

def submission_format_options():
 seen=set()
 options=[
  discord.SelectOption(
   label="Select format / mode if needed",
   value="__none__"
  )
 ]
 for variants in RAIDS.values():
  for variant in variants:
   if variant in seen:
    continue
   seen.add(variant)
   options.append(
    discord.SelectOption(label=variant,value=variant)
   )
 for mode in ("Normal","Awakened"):
  if mode not in seen:
   options.append(
    discord.SelectOption(label=mode,value=mode)
   )
 return options

def boss_submission_options():
 return [
  discord.SelectOption(label="Select if Raid PB",value="__none__"),
  *[
   discord.SelectOption(label=activity,value=activity)
   for activity in BOSSES
  ]
 ]

def parse_submission_details(raw):
 match=re.fullmatch(
  r"\s*(.+?)\s*[|,]\s*(\d{1,2}-\d{1,2}-\d{4}|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})\s*",
  raw.strip()
 )
 if not match:
  return None
 time_value,pb_date=match.groups()
 return pb_date,time_value

class SubmitModal(ui.Modal,title="NOVUS | PB Submission"):
 def __init__(self):
  super().__init__(timeout=300)

  self.target_select=ui.Select(
   placeholder="Choose PB type",
   options=submission_target_options(),
   min_values=1,
   max_values=1,
   required=True,
   custom_id="pb:submit:target"
  )
  self.format_select=ui.Select(
   placeholder="Choose raid format / DT2 mode",
   options=submission_format_options(),
   min_values=1,
   max_values=1,
   required=True,
   custom_id="pb:submit:format"
  )
  self.boss_select=ui.Select(
   placeholder="Choose boss if submitting a boss PB",
   options=boss_submission_options(),
   min_values=1,
   max_values=1,
   required=True,
   custom_id="pb:submit:boss"
  )
  self.details_input=ui.TextInput(
   placeholder="30.60 | 11/08/2026",
   max_length=40,
   custom_id="pb:submit:details"
  )
  self.members_select=ui.UserSelect(
   placeholder="Search Discord members",
   min_values=1,
   max_values=8,
   custom_id="pb:submit:members"
  )

  self.add_item(ui.Label(
   text="What are you submitting?",
   description="Choose one of the four raids or Boss PB.",
   component=self.target_select
  ))
  self.add_item(ui.Label(
   text="Raid format / boss mode",
   description="Choose the matching raid format. DT2 bosses use Normal or Awakened.",
   component=self.format_select
  ))
  self.add_item(ui.Label(
   text="Boss",
   description="Only used when Boss PB is selected above.",
   component=self.boss_select
  ))
  self.add_item(ui.Label(
   text="PB time & date",
   description="Use SS.ss or MM:SS.ss | MM/DD/YYYY or MM-DD-YYYY.",
   component=self.details_input
  ))
  self.add_item(ui.Label(
   text="Party members",
   description="Select every Novus member in the run.",
   component=self.members_select
  ))

 async def on_submit(self,i):
  target=self.target_select.values[0]
  selected_format=self.format_select.values[0]
  selected_boss=self.boss_select.values[0]

  if target.startswith("raid|||"):
   category="Raids"
   _,activity=target.split("|||",1)
   if selected_format not in RAIDS[activity]:
    valid=" · ".join(RAIDS[activity])
    return await i.response.send_message(
     f"Choose a valid format for **{activity}**: {valid}.",
     ephemeral=True
    )
   variant=selected_format
  else:
   category="Bosses"
   if selected_boss=="__none__":
    return await i.response.send_message(
     "Choose which boss the PB is for.",
     ephemeral=True
    )
   activity=selected_boss
   valid_modes=BOSSES[activity]
   if len(valid_modes)==1:
    variant=valid_modes[0]
   elif selected_format not in valid_modes:
    return await i.response.send_message(
     f"Choose **Normal** or **Awakened** for **{activity}**.",
     ephemeral=True
    )
   else:
    variant=selected_format

  parsed=parse_submission_details(self.details_input.value)
  if not parsed:
   return await i.response.send_message(
    "Use **SS.ss or MM:SS.ss | MM/DD/YYYY or MM-DD-YYYY**.",
    ephemeral=True
   )

  pb_date,time_value=parsed
  await submit(
   i,
   category,
   activity,
   variant,
   time_value,
   pb_date,
   self.members_select.values,
   ""
  )


@bot.tree.command(name="pbsubmit",description="Submit an eligible Novus PB for staff review")
@app_commands.guild_only()
async def pbsubmit(i:discord.Interaction):
 await i.response.send_modal(SubmitModal())

@bot.tree.command(name="pbproof",description="Attach proof to your pending submission")
@app_commands.guild_only()
@app_commands.describe(submission_id="Your PB submission number",url="Proof URL (optional)",attachment="Screenshot or video clip (optional)")
async def pbproof(i:discord.Interaction,submission_id:int,url:str="",attachment:discord.Attachment=None):
 r=await store.one("SELECT * FROM submissions WHERE id=? AND guild=?",(submission_id,i.guild_id))
 if not r or (r["submitter"]!=i.user.id and not is_staff(i)):
  return await i.response.send_message("PB not found or not yours.",ephemeral=True)
 if r["status"] not in ("pending","awaiting_proof"):
  return await i.response.send_message("PB is already resolved.",ephemeral=True)
 proof=attachment.url if attachment else url.strip()
 if not valid_url(proof):return await i.response.send_message("Provide a valid URL or attach an image/video.",ephemeral=True)
 if attachment and not (attachment.content_type or "").startswith(("image/","video/")):
  return await i.response.send_message("Only image/video files accepted.",ephemeral=True)
 await i.response.defer(ephemeral=True)
 if not await store.change(submission_id,r["status"],"pending",proof=proof):
  return await i.followup.send("Submission changed; retry.",ephemeral=True)
 updated=await store.one("SELECT * FROM submissions WHERE id=?",(submission_id,))
 await update_review(updated)
 await i.followup.send(f"Proof saved for PB #{submission_id}. Staff can review it now.",ephemeral=True)

@bot.tree.command(name="pbclear",description="Clear all Novus PB submissions and leaderboard records")
@app_commands.guild_only()
async def pbclear(i:discord.Interaction):
 if not is_council_or_founder(i):
  return await i.response.send_message("Council or Founder only.",ephemeral=True)

 await i.response.defer(ephemeral=True,thinking=True)
 rows=await store.all(
  "SELECT review_channel,review_message FROM submissions WHERE guild=?",
  (i.guild_id,)
 )
 deleted_cards=0
 for r in rows:
  if not r["review_channel"] or not r["review_message"]:
   continue
  try:
   ch=bot.get_channel(r["review_channel"]) or await bot.fetch_channel(r["review_channel"])
   msg=await ch.fetch_message(r["review_message"])
   await msg.delete()
   deleted_cards+=1
  except discord.HTTPException:
   pass

 await store.clear_guild(i.guild_id)
 await refresh_panel(i.guild_id)
 await i.followup.send(
  f"Cleared **{len(rows)}** PB submission(s). "
  f"Removed **{deleted_cards}** staff review card(s). "
  "The PB database is back to **0 submissions**.",
  ephemeral=True
 )

@bot.tree.command(name="checkemojis",description="Staff-only audit of Novus PB board emoji mappings")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def checkemojis(i:discord.Interaction):
 if not is_staff(i):
  return await i.response.send_message("Staff only.",ephemeral=True)
 await i.response.defer(ephemeral=True)
 await fetch_activity_emojis(i.guild)
 try:
  emojis=await i.guild.fetch_emojis()
 except discord.HTTPException:
  emojis=i.guild.emojis
 by_name={emoji.name.lower():emoji for emoji in emojis}
 found=[]
 missing=[]
 for activity,name in ACTIVITY_EMOJIS.items():
  if name.lower() in by_name:
   found.append(activity)
  else:
   missing.append(f"{activity}: expected `:{name}:`")
 lines=[
  f"**Novus PB Emoji Audit** · {len(found)}/{len(ACTIVITY_EMOJIS)} matched",
  f"Visible server emojis: {len(emojis)}",
  "**Missing mappings:**",
  *(missing if missing else ["None"]),
  "",
  "**Actual uploaded emoji names:**",
  ", ".join(sorted(e.name for e in emojis)) or "None",
  "",
  "CoX has no supplied icon in the original ZIP."
 ]
 await i.followup.send("\n".join(lines)[:1900],ephemeral=True)

@bot.tree.command(name="pbpanel",description="Create or refresh the persistent PB panel in this channel")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def pbpanel(i:discord.Interaction):
 if not is_staff(i):return await i.response.send_message("Staff only.",ephemeral=True)
 await i.response.defer(ephemeral=True)
 await fetch_activity_emojis(i.guild)
 me=i.guild.me
 perms=i.channel.permissions_for(me) if me else None
 if not perms or not perms.view_channel or not perms.send_messages:
  return await i.followup.send(
   "I need **View Channel** and **Send Messages** in this channel before I can create the PB panel.",
   ephemeral=True
  )

 # Remove the currently tracked PB board messages before recreating them.
 tracked_records=[
  await store.banner(i.guild_id),
  await store.panel(i.guild_id),
  await store.boss_panel(i.guild_id),
  await store.snapshot_panel(i.guild_id),
  await store.footer(i.guild_id),
 ]
 tracked_records.extend(
  await store.boss_boards(i.guild_id)
 )

 seen_messages=set()
 for record in tracked_records:
  if not record:
   continue
  key=(record["channel"],record["message"])
  if key in seen_messages:
   continue
  seen_messages.add(key)
  try:
   ch=bot.get_channel(record["channel"]) or await bot.fetch_channel(record["channel"])
   msg=await ch.fetch_message(record["message"])
   await msg.delete()
  except discord.HTTPException:
   pass

 await store.clear_boss_boards(i.guild_id)

 try:
  panel_msg=await i.channel.send(view=await Home.make(i.guild_id))

  # Post a temporary directory first so it stays above the leaderboards.
  boss_msg=await i.channel.send(view=BossDirectory())

  jump_links={}

  # Minigames first.
  for activity in ("Inferno","Fortis Colosseum","Fight Caves"):
   board_msg=await i.channel.send(
    view=await BossLeaderboard.make(
     i.guild_id,
     activity
    ),
    allowed_mentions=discord.AllowedMentions.none()
   )
   await store.set_boss_board(
    i.guild_id,
    activity,
    i.channel_id,
    board_msg.id
   )
   jump_links[activity]=board_msg.jump_url

  # Then the four raid boards, each showing Top 1-5 per format.
  for activity in RAIDS:
   board_msg=await i.channel.send(
    view=await RaidLeaderboard.make(
     i.guild_id,
     activity
    ),
    allowed_mentions=discord.AllowedMentions.none()
   )
   await store.set_boss_board(
    i.guild_id,
    activity,
    i.channel_id,
    board_msg.id
   )
   jump_links[activity]=board_msg.jump_url

  # Then the remaining bosses beginning with Alchemical Hydra.
  for activity in BOSSES:
   if activity in ("Inferno","Fortis Colosseum","Fight Caves"):
    continue
   board_msg=await i.channel.send(
    view=await BossLeaderboard.make(
     i.guild_id,
     activity
    ),
    allowed_mentions=discord.AllowedMentions.none()
   )
   await store.set_boss_board(
    i.guild_id,
    activity,
    i.channel_id,
    board_msg.id
   )
   jump_links[activity]=board_msg.jump_url

  # Turn each boss name into a native Discord jump link.
  await boss_msg.edit(
   view=BossDirectory(jump_links),
   allowed_mentions=discord.AllowedMentions.none()
  )

  snapshot_msg=await i.channel.send(
   view=await SnapshotPanel.make(i.guild_id),
   allowed_mentions=discord.AllowedMentions.none()
  )
  footer_msg=await i.channel.send(
   f"## [↑ CLICK TO SCROLL TO THE TOP]({panel_msg.jump_url})",
   allowed_mentions=discord.AllowedMentions.none()
  )

  await store.set_panel(i.guild_id,i.channel_id,panel_msg.id)
  await store.set_boss_panel(i.guild_id,i.channel_id,boss_msg.id)
  await store.set_snapshot_panel(i.guild_id,i.channel_id,snapshot_msg.id)
  await store.set_footer(i.guild_id,i.channel_id,footer_msg.id)
  async with store.lock:
   await store.conn.execute("DELETE FROM panel_banners WHERE guild=?",(i.guild_id,))
   await store.conn.commit()
  await i.followup.send(
   "Refreshed the Novus PB board with jump-linked raid and boss leaderboards.",
   ephemeral=True
  )
 except discord.Forbidden:
  logging.exception("PB panel send forbidden in channel %s",i.channel_id)
  await i.followup.send(
   "Discord blocked the PB board post. Give Novus PB **View Channel**, **Send Messages**, and **Read Message History** here, then run /pbpanel again.",
   ephemeral=True
  )
 except Exception as e:
  logging.exception("PB panel creation failed")
  await i.followup.send(
   f"PB panel creation failed: `{type(e).__name__}`. Check the Railway log for the matching traceback.",
   ephemeral=True
  )

if __name__=="__main__":
 if not TOKEN:raise RuntimeError("DISCORD_TOKEN environment variable is required")
 if not REVIEW_ID:raise RuntimeError("REVIEW_CHANNEL_ID environment variable is required")
 bot.run(TOKEN)
