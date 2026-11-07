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
GOLD=0xD9A75B
BLUE=0x346B9E
RAIDS={
 "Theatre of Blood":["Normal · Duo","Normal · Trio","Normal · 4-Man","Normal · 5-Man","Hard Mode · Trio","Hard Mode · 4-Man","Hard Mode · 5-Man"],
 "Chambers of Xeric":["Normal · Solo","Normal · Duo","Normal · Trio","Normal · 5-Man","Challenge Mode · Solo","Challenge Mode · Duo","Challenge Mode · Trio","Challenge Mode · 5-Man"],
 "Tombs of Amascut":["Expert · Solo","Expert · 8-Man"],
 "The Fractured Archive":["Solo","Duo","Trio","4-Man"]}
BOSSES={
 "Vardorvis":["Normal","Awakened"],"Duke Sucellus":["Normal","Awakened"],
 "Leviathan":["Normal","Awakened"],"The Whisperer":["Normal","Awakened"],
 "Phantom Muspah":["Standard"],"Phosani's Nightmare":["Standard"],
 "Gauntlet":["Regular","Corrupted"],"Inferno":["Standard"],
 "Colosseum":["Standard"],"Doom":["Standard"]}
CATS={"Raids":RAIDS,"Bosses":BOSSES}
MEDALS=["🥇","🥈","🥉","4.","5."]
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
  members TEXT NOT NULL,ms INTEGER NOT NULL,proof TEXT,status TEXT NOT NULL DEFAULT 'pending',
  reviewer INTEGER,review_channel INTEGER,review_message INTEGER,created TEXT,updated TEXT);
  CREATE INDEX IF NOT EXISTS pb_rank ON submissions(guild,category,activity,variant,status,ms);
  CREATE TABLE IF NOT EXISTS panels(guild INTEGER PRIMARY KEY,channel INTEGER,message INTEGER);""")
  await self.conn.commit()
 async def one(self,q,args=()):
  async with self.conn.execute(q,args) as c:return await c.fetchone()
 async def all(self,q,args=()):
  async with self.conn.execute(q,args) as c:return await c.fetchall()
 async def add(self,g,u,cat,act,v,m,ms,p):
  async with self.lock:
   c=await self.conn.execute("""INSERT INTO submissions(guild,submitter,category,activity,variant,members,ms,proof,created,updated)
   VALUES(?,?,?,?,?,?,?,?,?,?)""",(g,u,cat,act,v,m,ms,p,now(),now()))
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
 async def ranking(self,g,cat,a,v):
  return await self.all("""SELECT * FROM submissions WHERE guild=? AND category=? AND activity=? AND variant=?
  AND status='approved' ORDER BY ms,id LIMIT 5""",(g,cat,a,v))
 async def recent_approved(self,g,limit=5):
  return await self.all("""SELECT * FROM submissions
  WHERE guild=? AND status='approved'
  ORDER BY updated DESC,id DESC LIMIT ?""",(g,limit))
store=Store()
intents=discord.Intents.default()
class PB(commands.Bot):
 async def setup_hook(self):
  await store.open()
  self.add_view(Home())
  for r in await store.all("SELECT * FROM submissions WHERE status IN ('pending','awaiting_proof') AND review_message IS NOT NULL"):
   self.add_view(Review(r),message_id=r["review_message"])
  if GUILD_ID:
   guild=discord.Object(id=GUILD_ID)
   self.tree.copy_global_to(guild=guild)
   await self.tree.sync(guild=guild)
  else:await self.tree.sync()
bot=PB(command_prefix=commands.when_mentioned,intents=intents)
def is_staff(i):
 if not i.guild or not isinstance(i.user,discord.Member):return False
 m=i.user
 return m.guild_permissions.manage_guild or m.guild_permissions.administrator or bool(STAFF_ROLES.intersection(x.id for x in m.roles))

class Home(ui.LayoutView):
 def __init__(self,recent=None):
  super().__init__(timeout=None)
  box=ui.Container(accent_colour=GOLD)
  box.add_item(ui.TextDisplay(
   "## ✦ NOVUS\n"
   "**PERSONAL BEST LEADERBOARDS**\n\n"
   "Browse the five fastest approved records by activity and team size."
  ))
  box.add_item(ui.Separator())
  row=ui.ActionRow()
  for cat in CATS:
   b=ui.Button(label=cat,style=discord.ButtonStyle.secondary,custom_id="pb:home:"+cat.lower())
   async def clicked(i,chosen=cat):
    await i.response.send_message(view=await Browser.make(i.guild_id,chosen,0),ephemeral=True)
   b.callback=clicked;row.add_item(b)
  box.add_item(row)
  if recent:
   box.add_item(ui.Separator())
   lines=["### RECENTLY APPROVED"]
   for r in recent:
    lines.append(
     f"**{fmt(r['ms'])}** · {clean(r['activity'])} · {clean(r['variant'])}\n"
     f"-# {clean(r['members'])}"
    )
   box.add_item(ui.TextDisplay("\n".join(lines)))
  self.add_item(box)
 @classmethod
 async def make(cls,g):
  return cls(await store.recent_approved(g,5))

class Browser(ui.LayoutView):
 def __init__(self,g,cat,index,blocks):
  super().__init__(timeout=900)
  self.g=g;self.cat=cat;self.index=index
  activities=CATS[cat];name=list(activities)[index]
  head=ui.Container(accent_colour=GOLD)
  head.add_item(ui.TextDisplay(f"## ✦ NOVUS | {cat.upper()}\n### {clean(name)}\n-# {index+1} OF {len(activities)} · ALL VARIANTS BELOW"))
  row=ui.ActionRow()
  for label,offset in (("◀ Previous",-1),("Next ▶",1)):
   b=ui.Button(label=label,style=discord.ButtonStyle.secondary)
   async def move(i,delta=offset):
    await i.response.edit_message(view=await Browser.make(self.g,self.cat,(self.index+delta)%len(CATS[self.cat])))
   b.callback=move;row.add_item(b)
  other="Bosses" if cat=="Raids" else "Raids"
  b=ui.Button(label=other,style=discord.ButtonStyle.primary)
  async def swap(i):await i.response.edit_message(view=await Browser.make(self.g,other,0))
  b.callback=swap;row.add_item(b);head.add_item(row);self.add_item(head)
  for variant,results in blocks:
   lines=[f"### {clean(variant)} · TOP 5"]
   for k in range(5):
    if k>=len(results):lines.append(f"**{MEDALS[k]}** —")
    else:
     r=results[k]
     lines.append(f"**{MEDALS[k]}** **{fmt(r['ms'])}** · {clean(r['members'])}")
   section=ui.Container(accent_colour=BLUE)
   section.add_item(ui.TextDisplay("\n".join(lines)))
   self.add_item(section)
 @classmethod
 async def make(cls,g,cat,index):
  a=list(CATS[cat])[index]
  return cls(g,cat,index,[(v,await store.ranking(g,cat,a,v)) for v in CATS[cat][a]])

class Review(ui.LayoutView):
 def __init__(self,r):
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
     f"## ✦ NOVUS | PB Review\n"
     f"**{clean(r['activity'])}** · {clean(r['variant'])}\n"
     f"-# Submission #{r['id']} · Submitted by <@{r['submitter']}>"
    ),
    accessory=status_badge
   )
  )

  panel.add_item(ui.Separator())
  panel.add_item(
   ui.TextDisplay(
    f"-# SUBMITTED TIME\n"
    f"## {fmt(r['ms'])}\n"
    f"**{clean(r['members'])}**"
   )
  )

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
     "### Proof\n"
     "**Awaiting evidence**\n"
     "-# Screenshot, clip, or URL will appear here."
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
   decision_row.add_item(approve)
   decision_row.add_item(deny)
   panel.add_item(decision_row)

   proof_row=ui.ActionRow()
   request=ui.Button(
    label="Request Proof",
    style=discord.ButtonStyle.primary,
    custom_id=f"pb:review:request:{self.sid}"
   )
   async def request_clicked(i):await decide(i,self.sid,"request")
   request.callback=request_clicked
   proof_row.add_item(request)
   panel.add_item(proof_row)

  self.add_item(panel)

async def refresh_panel(g):
 r=await store.panel(g)
 if not r:return
 try:
  ch=bot.get_channel(r["channel"]) or await bot.fetch_channel(r["channel"])
  msg=await ch.fetch_message(r["message"])
  await msg.edit(view=await Home.make(g))
 except discord.HTTPException:logging.exception("Unable to refresh public panel")

async def update_review(r):
 if not r["review_message"]:return
 try:
  ch=bot.get_channel(r["review_channel"]) or await bot.fetch_channel(r["review_channel"])
  msg=await ch.fetch_message(r["review_message"])
  await msg.edit(view=Review(r))
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
 await i.response.edit_message(view=Review(updated))
 if choice=="approve":await refresh_panel(i.guild_id)
 if choice=="request":
  try:
   user=await bot.fetch_user(r["submitter"])
   await user.send(f"Your Novus PB #{sid} needs proof. Use /pbproof with submission_id {sid} in the Novus server.")
  except discord.HTTPException:logging.warning("Unable to DM submission owner")

async def submit(i,cat,act,variant,t,members,proof):
 try:ms=parse_ms(t)
 except ValueError as e:return await i.response.send_message(str(e),ephemeral=True)
 rsns=[x.strip() for x in members.split(",") if x.strip()]
 required=team_size(cat,variant)
 if not rsns or any(len(x)>12 for x in rsns) or len({x.lower() for x in rsns})!=len(rsns):
  return await i.response.send_message("Use unique, valid RuneScape names (12 characters max).",ephemeral=True)
 if required is not None and len(rsns)!=required:
  return await i.response.send_message(f"Expected {required} RSNs for this category.",ephemeral=True)
 if proof and not valid_url(proof):
  return await i.response.send_message("Provide an HTTP(S) proof link, or add proof later with /pbproof.",ephemeral=True)
 try:ch=bot.get_channel(REVIEW_ID) or await bot.fetch_channel(REVIEW_ID)
 except discord.HTTPException:return await i.response.send_message("Staff review channel not available.",ephemeral=True)
 await i.response.defer(thinking=True,ephemeral=True)
 sid=await store.add(i.guild_id,i.user.id,cat,act,variant,", ".join(rsns),ms,proof)
 r=await store.one("SELECT * FROM submissions WHERE id=?",(sid,))
 try:
  message=await ch.send(view=Review(r),allowed_mentions=discord.AllowedMentions.none())
  await store.attach_review(sid,ch.id,message.id)
 except discord.HTTPException:
  logging.exception("Staff review message failed")
  return await i.followup.send(f"Submission #{sid} saved, but staff delivery failed. Notify staff.",ephemeral=True)
 await i.followup.send(f"PB #{sid} submitted for staff review! "+("Proof received." if proof else "Add proof with /pbproof."),ephemeral=True)

def submission_select_options(category):
 options=[]
 for activity,variants in CATS[category].items():
  for variant in variants:
   options.append(
    discord.SelectOption(
     label=f"{activity} · {variant}",
     value=f"{activity}|||{variant}"
    )
   )
 return options

class SubmitModal(ui.Modal,title="NOVUS | PB Submission"):
 def __init__(self):
  super().__init__(timeout=300)

  self.raid_select=ui.Select(
   placeholder="Choose raid and mode",
   options=submission_select_options("Raids"),
   min_values=0,
   max_values=1,
   required=False,
   custom_id="pb:submit:raid"
  )
  self.boss_select=ui.Select(
   placeholder="Choose boss and mode",
   options=submission_select_options("Bosses"),
   min_values=0,
   max_values=1,
   required=False,
   custom_id="pb:submit:boss"
  )
  self.time_input=ui.TextInput(
   placeholder="14:32.60",
   max_length=20,
   custom_id="pb:submit:time"
  )
  self.members_input=ui.TextInput(
   placeholder="Vecs, Mohi, Hokage",
   max_length=240,
   custom_id="pb:submit:members"
  )
  self.proof_input=ui.TextInput(
   placeholder="https://...",
   required=False,
   max_length=500,
   custom_id="pb:submit:proof"
  )

  self.add_item(
   ui.Label(
    text="Raid PB",
    description="Choose this OR the Boss PB field below.",
    component=self.raid_select
   )
  )
  self.add_item(
   ui.Label(
    text="Boss PB",
    description="Choose this OR the Raid PB field above.",
    component=self.boss_select
   )
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
    text="Member RSNs",
    description="Comma-separated RuneScape names.",
    component=self.members_input
   )
  )
  self.add_item(
   ui.Label(
    text="Proof URL",
    description="Optional. Screenshot/video can be added later with /pbproof.",
    component=self.proof_input
   )
  )

 async def on_submit(self,i):
  raid=self.raid_select.values
  boss=self.boss_select.values
  if bool(raid)==bool(boss):
   return await i.response.send_message(
    "Choose exactly one PB activity: either a Raid or a Boss.",
    ephemeral=True
   )

  category="Raids" if raid else "Bosses"
  choice=(raid or boss)[0]
  activity,variant=choice.split("|||",1)

  await submit(
   i,
   category,
   activity,
   variant,
   self.time_input.value,
   self.members_input.value,
   self.proof_input.value.strip()
  )

@bot.tree.command(name="pbsubmission",description="Submit a new PB for staff review")
@app_commands.guild_only()
async def pbsubmission(i:discord.Interaction):
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
 old=await store.panel(i.guild_id)
 if old:
  try:
   ch=bot.get_channel(old["channel"]) or await bot.fetch_channel(old["channel"])
   msg=await ch.fetch_message(old["message"])
   await msg.edit(view=await Home.make(i.guild_id))
   return await i.followup.send(f"Refreshed the existing panel in <#{ch.id}>.",ephemeral=True)
  except discord.HTTPException:
   logging.exception("Unable to refresh existing PB panel; creating a new one")
 try:
  msg=await i.channel.send(view=await Home.make(i.guild_id))
  await store.set_panel(i.guild_id,i.channel_id,msg.id)
  await i.followup.send("Created the PB panel. Pin the message.",ephemeral=True)
 except discord.Forbidden:
  logging.exception("PB panel send forbidden in channel %s",i.channel_id)
  await i.followup.send(
   "Discord blocked the panel post. Give Novus PB **View Channel**, **Send Messages**, **Read Message History**, and **Embed Links** here, then run /pbpanel again.",
   ephemeral=True
  )
 except Exception as e:
  logging.exception("PB panel creation failed")
  await i.followup.send(
   f"PB panel creation failed: \`{type(e).__name__}\`. Check the Railway log for the matching traceback.",
   ephemeral=True
  )

if __name__=="__main__":
 if not TOKEN:raise RuntimeError("DISCORD_TOKEN environment variable is required")
 if not REVIEW_ID:raise RuntimeError("REVIEW_CHANNEL_ID environment variable is required")
 bot.run(TOKEN)
