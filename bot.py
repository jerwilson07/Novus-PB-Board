import os, re, asyncio, logging
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
PB_BANNER_URL="https://raw.githubusercontent.com/jerwilson07/Novus-PB-Board/e56d115997dde7d1696ef4c535ce366da87ba84b/assets/novus_pb_banner.jpg"
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
 "Corrupted Gauntlet":["Standard"],
 "Demonic Brutus":["Standard"],
 "Doom of Mokhaiotl":["Standard"],
 "Gauntlet":["Standard"],
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
MEDALS=["🥇","🥈","🥉","4.","5."]

def public_members(r):
 try: raw=r["member_ids"]
 except (KeyError,IndexError): raw=None
 ids=[x.strip() for x in (raw or "").split(",") if x.strip().isdigit()]
 return " · ".join(f"<@{x}>" for x in ids) if ids else clean(r["members"])

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
def clean(v): return discord.utils.escape_mentions(discord.utils.escape_markdown(str(v)))
def valid_url(v):
 try:
  x=urlparse(v); return x.scheme in ("http","https") and bool(x.netloc)
 except ValueError: return False
def parse_ms(s):
 parts=s.strip().split(":")
 if len(parts) not in (2,3) or any(not x.isdecimal() for x in parts[:-1]): raise ValueError("Use MM:SS.ss or HH:MM:SS.ss.")
 if not re.fullmatch(r"\d{1,2}(?:\.\d{1,3})?",parts[-1]): raise ValueError("Invalid seconds.")
 secs,*fraction=parts[-1].split(".")
 seconds=int(secs); ms=int(fraction[0].ljust(3,"0")) if fraction else 0
 minutes=int(parts[-2]); hours=int(parts[0]) if len(parts)==3 else 0
 if seconds>59 or (len(parts)==3 and minutes>59): raise ValueError("Invalid seconds/minutes.")
 total=((hours*60+minutes)*60+seconds)*1000+ms
 if not 0<total<=86400000: raise ValueError("Time must be positive and within 24h.")
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
def team_size(cat,variant):
 if cat=="Bosses" or "Solo" in variant:return 1
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
  CREATE TABLE IF NOT EXISTS panel_snapshot(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);""")
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
 async def snapshot_panel(self,g):return await self.one("SELECT * FROM panel_snapshot WHERE guild=?",(g,))
 async def set_snapshot_panel(self,g,ch,msg):
  async with self.lock:
   await self.conn.execute("""INSERT INTO panel_snapshot VALUES(?,?,?) ON CONFLICT(guild) DO UPDATE
   SET channel=excluded.channel,message=excluded.message""",(g,ch,msg))
   await self.conn.commit()
 async def ranking(self,g,cat,a,v):
  return await self.all("""SELECT * FROM submissions WHERE guild=? AND category=? AND activity=? AND variant=?
  AND status='approved' ORDER BY ms,id LIMIT 5""",(g,cat,a,v))
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
 async def raid_top3(self,g,activity):
  return await self.all("""SELECT * FROM submissions
  WHERE guild=? AND category='Raids' AND activity=? AND status='approved'
  ORDER BY ms,id LIMIT 3""",(g,activity))
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

@bot.event
async def on_ready():
 logging.info("Novus PB bot ready as %s (%s)",bot.user,bot.user.id)

def is_staff(i):
 if not i.guild or not isinstance(i.user,discord.Member):return False
 m=i.user
 return m.guild_permissions.manage_guild or m.guild_permissions.administrator or bool(STAFF_ROLES.intersection(x.id for x in m.roles))

def is_council_or_founder(i):
 if not i.guild or not isinstance(i.user,discord.Member):return False
 allowed={"council","founder"}
 return any(role.name.casefold() in allowed for role in i.user.roles)

class RulesCard(ui.LayoutView):
 def __init__(self):
  super().__init__(timeout=180)
  panel=ui.Container(accent_colour=GOLD)
  panel.add_item(ui.TextDisplay(
   "## ✦ NOVUS · PB RULES\n"
   "-# PLEASE REVIEW BEFORE SUBMITTING"
  ))
  panel.add_item(ui.Separator())
  panel.add_item(ui.TextDisplay(
   "**1. Novus-only records.** Your PB must have been achieved while you were "
   "a member of Novus. Older PBs are not eligible.\n\n"
   "**2. Group PBs.** Every player involved must have been a Novus member "
   "on the date of the run. List every participant accurately.\n\n"
   "**3. Record details.** Include the PB date, completion time, activity, "
   "mode/team size, and all involved players.\n\n"
   "**4. Proof.** Provide a dated screenshot, clip, or evidence URL showing "
   "the run and participants. Use **/pbproof** after submission to attach it. "
   "Staff must verify eligibility and proof before approval."
  ))
  self.add_item(panel)


class Home(ui.LayoutView):
 def __init__(self):
  super().__init__(timeout=None)

  hero=ui.Container(accent_colour=GOLD)
  banner=ui.MediaGallery()
  banner.add_item(media=PB_BANNER_URL)
  hero.add_item(banner)
  hero.add_item(ui.TextDisplay(
   "## ✦ NOVUS · PERSONAL BESTS"
  ))
  hero.add_item(ui.Separator())

  hero.add_item(ui.TextDisplay("**RAIDS**"))
  raid_row=ui.ActionRow()
  for raid_index,activity in enumerate(RAIDS):
   raid_button=ui.Button(
    label=RAID_LABELS[activity],
    style=discord.ButtonStyle.primary,
    custom_id=f"pb:home:raid:{raid_index}"
   )
   async def open_raid(i,idx=raid_index):
    await i.response.send_message(
     view=await RaidBrowser.make(i.guild_id,idx,0),
     ephemeral=True
    )
   raid_button.callback=open_raid
   raid_row.add_item(raid_button)
  hero.add_item(raid_row)

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
   await i.response.send_message(view=SubmitStart(),ephemeral=True)
  async def open_rules(i):
   await i.response.send_message(view=RulesCard(),ephemeral=True)
  submit.callback=open_submit
  rules.callback=open_rules
  actions.add_item(submit)
  actions.add_item(rules)
  hero.add_item(actions)

  self.add_item(hero)


class SnapshotPanel(ui.LayoutView):
 def __init__(self,raid_leaders=None,recent=None):
  super().__init__(timeout=None)
  raid_leaders=raid_leaders or {}
  recent=recent or []

  records=ui.Container(accent_colour=BLUE)
  snapshot=["### RAID SNAPSHOT"]
  for activity in RAIDS:
   results=raid_leaders.get(activity,[])
   snapshot.append(f"\n**{RAID_LABELS[activity]} · {clean(activity)}**")
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
  return cls(leaders,await store.recent_approved(g,3))


class BossDirectory(ui.LayoutView):
 def __init__(self):
  super().__init__(timeout=None)

  panel=ui.Container(accent_colour=BLUE)
  panel.add_item(ui.TextDisplay(
   "## BOSSES\n"
   "-# SELECT A CATEGORY"
  ))

  groups=[
   ("MINIGAMES",[
    "Inferno","Fortis Colosseum","Fight Caves"
   ]),
   ("SLAYER BOSSES",[
    "Alchemical Hydra","Araxxor","Grotesque Guardians"
   ]),
   ("SOLO & DUO BOSSES",[
    "Corrupted Gauntlet","Demonic Brutus","Doom of Mokhaiotl",
    "Gauntlet","Mad Angel","Maggot King","Phantom Muspah",
    "Phosani's Nightmare","Royal Titans","Vorkath","Yama","Zulrah"
   ]),
   ("DT2 BOSSES",[
    "Duke Sucellus","The Leviathan","Vardorvis","The Whisperer"
   ])
  ]

  boss_names=list(BOSSES)
  for group_index,(heading,names) in enumerate(groups):
   panel.add_item(ui.TextDisplay(
    ("\n" if group_index else "") + f"**{heading}**"
   ))

   row_size=2 if heading in ("SOLO & DUO BOSSES","DT2 BOSSES") else 3
   for row_start in range(0,len(names),row_size):
    row=ui.ActionRow()
    for name in names[row_start:row_start+row_size]:
     idx=boss_names.index(name)
     button=ui.Button(
      label=name,
      style=discord.ButtonStyle.secondary,
      custom_id=f"pb:bossdir:{idx}"
     )
     async def open_boss(i,target=idx):
      await i.response.send_message(
       view=await Browser.make(i.guild_id,"Bosses",target),
       ephemeral=True
      )
     button.callback=open_boss
     row.add_item(button)
    panel.add_item(row)

  self.add_item(panel)


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
   f"## ✦ NOVUS · {RAID_LABELS[activity]}\n"
   f"**{clean(activity)}**"
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
   await i.response.send_message(view=SubmitStart(),ephemeral=True)
  async def open_rules(i):
   await i.response.send_message(view=RulesCard(),ephemeral=True)
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
   await i.response.send_message(view=SubmitStart(),ephemeral=True)
  async def open_rules(i):
   await i.response.send_message(view=RulesCard(),ephemeral=True)
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
 def __init__(self,r,leader=None):
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
  panel.add_item(
   ui.TextDisplay(
    f"-# PB DATE · TIME\n"
    f"**{clean(r['pb_date'] or 'Not recorded')}** · **{fmt(r['ms'])}**\n"
    f"**{review_members(r)}**"
   )
  )

  if active:
   if leader is None:
    comparison=(
     "### FIRST CATEGORY RECORD\n"
     "-# No approved record yet."
    )
   elif r["ms"]<leader["ms"]:
    comparison=(
     "### POTENTIAL NEW #1\n"
     f"**{fmt(r['ms'])}** · current #1 **{fmt(leader['ms'])}**\n"
     f"-# Faster by {fmt(leader['ms']-r['ms'])}"
    )
   elif r["ms"]==leader["ms"]:
    comparison=(
     "### TIES CURRENT #1\n"
     f"**{fmt(r['ms'])}** · same as current #1"
    )
   else:
    comparison=(
     "### CURRENT #1\n"
     f"**{fmt(leader['ms'])}** · submitted **{fmt(r['ms'])}**"
    )
   panel.add_item(ui.TextDisplay(comparison))

  panel.add_item(ui.Separator())
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
  if r["status"] in ("pending","awaiting_proof"):
   leader=await store.best_approved(
    r["guild"],r["category"],r["activity"],r["variant"]
   )
  return cls(r,leader)


async def refresh_panel(g):
 r=await store.snapshot_panel(g)
 if not r:return
 try:
  ch=bot.get_channel(r["channel"]) or await bot.fetch_channel(r["channel"])
  msg=await ch.fetch_message(r["message"])
  await msg.edit(
   view=await SnapshotPanel.make(g),
   allowed_mentions=discord.AllowedMentions.none()
  )
 except discord.HTTPException:logging.exception("Unable to refresh public panel")

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
 if choice=="approve":await refresh_panel(i.guild_id)
 if choice=="request":
  try:
   user=await bot.fetch_user(r["submitter"])
   await user.send(f"Your Novus PB #{sid} needs proof. Use /pbproof with submission_id {sid} in the Novus server.")
  except discord.HTTPException:logging.warning("Unable to DM submission owner")

async def submit(i,cat,act,variant,t,pb_date,members,proof=""):
 try:ms=parse_ms(t)
 except ValueError as e:return await i.response.send_message(str(e),ephemeral=True)

 raw_date=pb_date.strip()
 parsed_date=None
 for date_format in ("%Y-%m-%d","%m/%d/%Y"):
  try:
   parsed_date=datetime.strptime(raw_date,date_format).date()
   break
  except ValueError:
   pass
 if parsed_date is None:
  return await i.response.send_message(
   "Enter the PB date as YYYY-MM-DD or MM/DD/YYYY.",
   ephemeral=True
  )
 if parsed_date>datetime.now(timezone.utc).date():
  return await i.response.send_message(
   "The PB date cannot be in the future.",
   ephemeral=True
  )
 normalized_date=parsed_date.isoformat()

 required=team_size(cat,variant)
 if not members:
  return await i.response.send_message("Select at least one party member.",ephemeral=True)
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
  + ("Proof received." if proof else "Add proof with /pbproof."),
  ephemeral=True
 )

def submission_activity_options(category):
 return [
  discord.SelectOption(
   label=activity,
   value=activity,
   description=" / ".join(variants)[:100]
  )
  for activity,variants in CATS[category].items()
 ]

class SubmitStart(ui.LayoutView):
 def __init__(self):
  super().__init__(timeout=300)
  panel=ui.Container(accent_colour=GOLD)
  panel.add_item(ui.TextDisplay(
   "## ✦ NOVUS · SUBMIT PB\n"
   "-# CHOOSE A CATEGORY"
  ))
  row=ui.ActionRow()
  raids=ui.Button(label="Raids",style=discord.ButtonStyle.primary)
  bosses=ui.Button(label="Bosses",style=discord.ButtonStyle.secondary)

  async def choose_raids(i):
   await i.response.edit_message(view=SubmitActivityPicker("Raids"))
  async def choose_bosses(i):
   await i.response.edit_message(view=SubmitActivityPicker("Bosses"))

  raids.callback=choose_raids
  bosses.callback=choose_bosses
  row.add_item(raids)
  row.add_item(bosses)
  panel.add_item(row)
  self.add_item(panel)


class SubmitActivityPicker(ui.LayoutView):
 def __init__(self,category):
  super().__init__(timeout=300)
  self.category=category

  panel=ui.Container(accent_colour=BLUE)
  panel.add_item(ui.TextDisplay(
   f"## {category.upper()}\n"
   "-# SELECT AN ACTIVITY"
  ))

  select=ui.Select(
   placeholder="Choose raid" if category=="Raids" else "Choose boss",
   options=submission_activity_options(category),
   min_values=1,
   max_values=1
  )

  async def choose_activity(i):
   activity=select.values[0]
   variants=CATS[self.category][activity]
   if len(variants)==1:
    await i.response.send_modal(
     SubmitDetailsModal(self.category,activity,variants[0])
    )
   else:
    await i.response.edit_message(
     view=SubmitModePicker(self.category,activity)
    )

  select.callback=choose_activity
  row=ui.ActionRow()
  row.add_item(select)
  panel.add_item(row)

  back_row=ui.ActionRow()
  back=ui.Button(label="Back",style=discord.ButtonStyle.secondary)
  async def go_back(i):
   await i.response.edit_message(view=SubmitStart())
  back.callback=go_back
  back_row.add_item(back)
  panel.add_item(back_row)

  self.add_item(panel)


class SubmitModePicker(ui.LayoutView):
 def __init__(self,category,activity):
  super().__init__(timeout=300)
  self.category=category
  self.activity=activity

  panel=ui.Container(accent_colour=BLUE)
  panel.add_item(ui.TextDisplay(
   f"## {clean(activity)}\n"
   "-# SELECT MODE / TEAM SIZE"
  ))

  select=ui.Select(
   placeholder="Choose mode / team size",
   options=[
    discord.SelectOption(label=variant,value=variant)
    for variant in CATS[category][activity]
   ],
   min_values=1,
   max_values=1
  )

  async def choose_variant(i):
   await i.response.send_modal(
    SubmitDetailsModal(self.category,self.activity,select.values[0])
   )

  select.callback=choose_variant
  row=ui.ActionRow()
  row.add_item(select)
  panel.add_item(row)

  back_row=ui.ActionRow()
  back=ui.Button(label="Back",style=discord.ButtonStyle.secondary)
  async def go_back(i):
   await i.response.edit_message(view=SubmitActivityPicker(self.category))
  back.callback=go_back
  back_row.add_item(back)
  panel.add_item(back_row)

  self.add_item(panel)


class SubmitDetailsModal(ui.Modal,title="NOVUS | PB Submission"):
 def __init__(self,category,activity,variant):
  super().__init__(timeout=300)
  self.category=category
  self.activity=activity
  self.variant=variant

  self.time_input=ui.TextInput(
   placeholder="14:32.60",
   max_length=20,
   custom_id="pb:submit:time"
  )
  self.date_input=ui.TextInput(
   placeholder="YYYY-MM-DD",
   required=True,
   min_length=8,
   max_length=10,
   custom_id="pb:submit:date"
  )

  required_members=team_size(category,variant)
  self.members_select=ui.UserSelect(
   placeholder="Search Discord members",
   min_values=required_members or 1,
   max_values=required_members or 8,
   custom_id="pb:submit:members"
  )

  self.proof_input=ui.TextInput(
   placeholder="https://... (optional)",
   required=False,
   max_length=500,
   custom_id="pb:submit:proof"
  )

  self.add_item(
   ui.Label(
    text="Completion time",
    description="Use MM:SS.ss or HH:MM:SS.ss.",
    component=self.time_input
   )
  )
  self.add_item(
   ui.Label(
    text="PB date",
    description="Use YYYY-MM-DD.",
    component=self.date_input
   )
  )
  self.add_item(
   ui.Label(
    text="Party members",
    description=(
     f"Select exactly {required_members} member(s)."
     if required_members else
     "Select every Novus member in the run."
    ),
    component=self.members_select
   )
  )
  self.add_item(
   ui.Label(
    text="Proof URL",
    description="Optional. You can also add proof later with /pbproof.",
    component=self.proof_input
   )
  )

 async def on_submit(self,i):
  await submit(
   i,
   self.category,
   self.activity,
   self.variant,
   self.time_input.value,
   self.date_input.value,
   self.members_select.values,
   self.proof_input.value.strip()
  )

@bot.tree.command(name="pbsubmit",description="Submit an eligible Novus PB for staff review")
@app_commands.guild_only()
async def pbsubmit(i:discord.Interaction):
 await i.response.send_message(
  view=SubmitStart(),
  ephemeral=True
 )

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

@bot.tree.command(name="pbpanel",description="Create or refresh the persistent PB panel in this channel")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def pbpanel(i:discord.Interaction):
 if not is_staff(i):return await i.response.send_message("Staff only.",ephemeral=True)
 await i.response.defer(ephemeral=True)
 me=i.guild.me
 perms=i.channel.permissions_for(me) if me else None
 if not perms or not perms.view_channel or not perms.send_messages:
  return await i.followup.send(
   "I need **View Channel** and **Send Messages** in this channel before I can create the PB panel.",
   ephemeral=True
  )

 # Remove the currently tracked PB board messages before recreating them.
 for record in (await store.banner(i.guild_id),await store.panel(i.guild_id),await store.boss_panel(i.guild_id),await store.snapshot_panel(i.guild_id)):
  if not record:
   continue
  try:
   ch=bot.get_channel(record["channel"]) or await bot.fetch_channel(record["channel"])
   msg=await ch.fetch_message(record["message"])
   await msg.delete()
  except discord.HTTPException:
   pass

 try:
  panel_msg=await i.channel.send(view=Home())
  boss_msg=await i.channel.send(view=BossDirectory())
  snapshot_msg=await i.channel.send(
   view=await SnapshotPanel.make(i.guild_id),
   allowed_mentions=discord.AllowedMentions.none()
  )
  await store.set_panel(i.guild_id,i.channel_id,panel_msg.id)
  await store.set_boss_panel(i.guild_id,i.channel_id,boss_msg.id)
  await store.set_snapshot_panel(i.guild_id,i.channel_id,snapshot_msg.id)
  async with store.lock:
   await store.conn.execute("DELETE FROM panel_banners WHERE guild=?",(i.guild_id,))
   await store.conn.commit()
  await i.followup.send(
   "Refreshed the Novus PB board with separate Raids and Bosses panels.",
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
