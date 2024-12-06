import os
import json
import discord
from discord.ext import commands
from discord import app_commands, Embed, Interaction, ui
from datetime import datetime
from typing import Optional
import pytz
import asyncio

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
EMBED_COLOR = os.getenv("EMBED_COLOR")  # Baby pink color
TIMEZONE = os.getenv("TIMEZONE", "America/New_York")

RAW_ADMIN_ROLE_IDS = os.getenv("ADMIN_ROLE_IDS", "")
ROLE_IDS_STRINGS = RAW_ADMIN_ROLE_IDS.split(",")

ADMIN_ROLE_IDS = []
for role_id in ROLE_IDS_STRINGS:
    role_id = role_id.strip()  # Remove extra spaces
    if role_id.isdigit():     # Check if it's a valid number
        ADMIN_ROLE_IDS.append(int(role_id))

ITEMS_PER_PAGE = 4

# Path to the jobs.json file
JOBS_FILE = "jobs.json"

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class DeleteJobButton(ui.View):
    def __init__(self, job_id: int):
        super().__init__()
        self.job_id = job_id

    @ui.button(label="Delete Job", style=discord.ButtonStyle.danger)
    async def delete_job(self, interaction: Interaction, button: ui.Button):
        # Check admin permissions
        is_admin = await check_admin_role(interaction)
        if not is_admin:
            await interaction.response.send_message(
                "You do not have permission to delete this job.", ephemeral=True
            )
            return

        # Load jobs and remove the specific job
        data = load_jobs()
        job = next((job for job in data["jobs"] if job["id"] == self.job_id), None)
        
        if not job:
            await interaction.response.send_message("Job not found.", ephemeral=True)
            return

        # Remove the job from the list
        data["jobs"] = [j for j in data["jobs"] if j["id"] != self.job_id]
        save_jobs(data)

        # Delete the original message with the job embed
        await interaction.message.delete()

        # Confirm deletion
        await interaction.response.send_message(f"Job {self.job_id} has been deleted.", ephemeral=True)

# Helper Functions
def load_jobs():
    """Load jobs from the JSON file."""
    if not os.path.exists(JOBS_FILE):
        return {"counter": 0, "jobs": []}  # Initialize structure if file doesn't exist
    with open(JOBS_FILE, "r") as file:
        return json.load(file)


def save_jobs(data):
    """Save jobs to the JSON file."""
    with open(JOBS_FILE, "w") as file:
        json.dump(data, file, indent=4)


def format_embed(job):
    """Helper function to create an enhanced, more spaced-out embed for a job."""
    # Format accepted, declined, and tentative users
    accepted_users = "No one yet" if not job["accepted"] else "\n".join(
        [f"<@{user}>" for user in job["accepted"]]
    )
    declined_users = "No one yet" if not job["declined"] else "\n".join(
        [f"<@{user}>" for user in job["declined"]]
    )
    tentative_users = "No one yet" if not job["tentative"] else "\n".join(
        [f"<@{user}>" for user in job["tentative"]]
    )

    embed = Embed(
        title="Job Scheduling",
        color=int(EMBED_COLOR.lstrip('#'), 16),
    )
    embed.add_field(name="Time", value=f"{job['time']}", inline=False)
    embed.add_field(name="Location", value=f"{job['location']}", inline=False)
    # Add reaction status fields with more spacing
    embed.add_field(
        name=f"✅ Accepted ({len(job['accepted'])})", 
        value=f"\n{accepted_users}", 
        inline=True
    )
    embed.add_field(
        name=f"❌ Declined ({len(job['declined'])})", 
        value=f"\n{declined_users}", 
        inline=True
    )
    embed.add_field(
        name=f"❓ Tentative ({len(job['tentative'])})", 
        value=f"\n{tentative_users}", 
        inline=True
    )

    # Enhanced footer with more information
    embed.set_footer(
        text=f"Created by {job['created_by']} | Job ID: {job['id']}"
    )

    return embed


async def check_admin_role(interaction: Interaction):
    """Helper function to check admin permissions."""
    is_owner = interaction.user == interaction.guild.owner
    user_roles = [role.id for role in interaction.user.roles]
    has_admin_role = any(role_id in user_roles for role_id in ADMIN_ROLE_IDS)
    return is_owner or has_admin_role


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reactions added to job embed."""
    if payload.message_id is None:
        return

    # Check if the message contains the embed
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    if not message.embeds:
        return

    embed = message.embeds[0]
    # Extract job_id from the footer text by splitting based on "Job ID: "
    footer_text = embed.footer.text.split("Job ID: ")
    if len(footer_text) < 2:
        return  # Prevent errors if the footer doesn't contain the expected text format
    job_id = int(footer_text[-1].split(" | ")[0])  # Get the job ID
    data = load_jobs()

    # Find the job
    job = next((job for job in data["jobs"] if job["id"] == job_id), None)
    if not job:
        return

    # Determine the status from the emoji
    if str(payload.emoji) == "✅":
        status = "accepted"
    elif str(payload.emoji) == "❌":
        status = "declined"
    elif str(payload.emoji) == "❓":
        status = "tentative"
    else:
        return  # Ignore other reactions

    # Add the user's reaction to the appropriate list
    if payload.user_id != bot.user.id:  # Don't allow the bot to react
        if payload.user_id not in job[status]:
            job[status].append(payload.user_id)
            save_jobs(data)

            # Update the embed with the new count using format_embed
            new_embed = format_embed(job)
            await message.edit(embed=new_embed)


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """Handle reactions removed from job embed."""
    if payload.message_id is None:
        return

    # Check if the message contains the embed
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    if not message.embeds:
        return

    embed = message.embeds[0]
    # Extract job_id from the footer text by splitting based on "Job ID: "
    footer_text = embed.footer.text.split("Job ID: ")
    if len(footer_text) < 2:
        return  # Prevent errors if the footer doesn't contain the expected text format
    job_id = int(footer_text[-1].split(" | ")[0])  # Get the job ID
    data = load_jobs()

    # Find the job
    job = next((job for job in data["jobs"] if job["id"] == job_id), None)
    if not job:
        return

    # Determine the status from the emoji
    if str(payload.emoji) == "✅":
        status = "accepted"
    elif str(payload.emoji) == "❌":
        status = "declined"
    elif str(payload.emoji) == "❓":
        status = "tentative"
    else:
        return  # Ignore other reactions

    # Remove the user's reaction from the appropriate list
    if payload.user_id != bot.user.id:  # Don't allow the bot to react
        if payload.user_id in job[status]:
            job[status].remove(payload.user_id)
            save_jobs(data)

            # Update the embed with the new count using format_embed
            new_embed = format_embed(job)
            await message.edit(embed=new_embed)


@bot.tree.command(name="createjob", description="Create a new job.")
@app_commands.describe(
    date="The date of the job (DD/MM/YYYY)",
    time="The time of the job (HH:mm, 24-hour format)",
    location="The location of the job",
    details="Additional details (optional)",
)
async def createjob(
    interaction: Interaction,
    date: str,
    time: str,
    location: str,
    details: str = None,
):
    if not await check_admin_role(interaction):
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )
        return

    try:
        job_datetime = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")
        job_datetime = pytz.timezone(TIMEZONE).localize(job_datetime)
    except ValueError:
        await interaction.response.send_message(
            "Invalid date or time format. Use DD/MM/YYYY for date and HH:mm (24-hour) for time.",
            ephemeral=True,
        )
        return

    # Defer the response to allow time for job creation
    await interaction.response.defer()

    # Load jobs and add the new job
    data = load_jobs()
    job_id = data["counter"] + 1
    job = {
        "id": job_id,
        "time": job_datetime.strftime("%A %d %B %Y %H:%M"),
        "location": location,
        "details": details or "No details provided",
        "accepted": [],
        "declined": [],
        "tentative": [],
        "created_by": interaction.user.name,
    }
    data["jobs"].append(job)
    data["counter"] = job_id
    save_jobs(data)

    # Use format_embed to create an embed
    embed = format_embed(job)

    # Send the embed with delete button and reactions
    message = await interaction.followup.send(embed=embed, view=DeleteJobButton(job_id))

    # Add reactions to the message
    await message.add_reaction("✅")
    await message.add_reaction("❌")
    await message.add_reaction("❓")


# View jobs command
@bot.tree.command(name="viewjobs", description="View all active jobs.")
async def viewjobs(interaction: Interaction):
    data = load_jobs()
    jobs = data["jobs"]
    if not jobs:
        await interaction.response.send_message("There are no available jobs.", ephemeral=True)
        return

    total_pages = (len(jobs) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE  # Calculate total pages
    page = 1  # Start at page 1

    def create_job_list_embed(page: int):
        embed = Embed(
            title="Active Jobs",
            color=int(EMBED_COLOR.lstrip('#'), 16),
        )
        start = (page - 1) * ITEMS_PER_PAGE
        for job in jobs[start: start + ITEMS_PER_PAGE]:
            embed.add_field(
                name=f"Job {job['id']}",
                value=f"Time: {job['time']}\nLocation: {job['location']}",
                inline=False,
            )
        embed.set_footer(text=f"Page {page}/{total_pages}")
        return embed

    await interaction.response.defer()  # Defer the interaction to allow follow-up
    embed = create_job_list_embed(page)
    message = await interaction.followup.send(embed=embed, wait=True)

    # Add pagination reactions
    try:
        await message.add_reaction("◀️")
        await message.add_reaction("▶️")
    except Exception as e:
        await interaction.followup.send("Failed to add reactions. Check bot permissions.")
        return

    def check(reaction, user):
        return (
            user == interaction.user
            and str(reaction.emoji) in ["◀️", "▶️"]
            and reaction.message.id == message.id
        )

    while True:
        try:
            reaction, user = await bot.wait_for("reaction_add", check=check, timeout=60)
            if str(reaction.emoji) == "◀️" and page > 1:
                page -= 1
            elif str(reaction.emoji) == "▶️" and page < total_pages:
                page += 1
            else:
                await message.remove_reaction(reaction, user)
                continue

            embed = create_job_list_embed(page)
            await message.edit(embed=embed)
            await message.remove_reaction(reaction, user)

        except asyncio.TimeoutError:
            break

    # Clear reactions after timeout
    try:
        await message.clear_reactions()
    except Exception:
        pass

@bot.tree.command(name="editjob", description="Edit details of an existing job.")
@app_commands.describe(
    job_id="The ID of the job you want to edit",
    time="The new time (format: DD/MM/YYYY HH:mm)",
    location="The new location",
    details="The new details"
)
async def editjob(
    interaction: Interaction,
    job_id: int,
    time: Optional[str] = None,
    location: Optional[str] = None,
    details: Optional[str] = None
):
    if not await check_admin_role(interaction):
        await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )
        return

    # Load jobs and find the job by ID
    data = load_jobs()
    job = next((job for job in data["jobs"] if job["id"] == job_id), None)

    if not job:
        await interaction.response.send_message("Job not found.", ephemeral=True)
        return

    # Edit job details if provided
    if time:
        try:
            job_datetime = datetime.strptime(time, "%d/%m/%Y %H:%M")
            job_datetime = pytz.timezone(TIMEZONE).localize(job_datetime)
            job["time"] = job_datetime.strftime("%A %d %B %Y %H:%M")
        except ValueError:
            await interaction.response.send_message(
                "Invalid time format. Use DD/MM/YYYY for date and HH:mm (24-hour) for time.",
                ephemeral=True,
            )
            return

    if location:
        job["location"] = location

    if details:
        job["details"] = details

    # Save the updated job back to the JSON file
    save_jobs(data)

    # Create an embed for the updated job
    embed = format_embed(job)

    # Edit the original message with the updated embed
    channel = interaction.channel
    async for message in channel.history(limit=100):
        if message.embeds and message.embeds[0].title == "Scheduled Job" and job["id"] in message.embeds[0].footer.text:
            await message.edit(embed=embed)
            break

    # Respond to the interaction
    await interaction.response.send_message(f"Job {job_id} has been updated successfully.", ephemeral=True)

@bot.tree.command(name="info", description="View all listed commands")
@app_commands.describe()
async def info(interaction: Interaction):
    embed = discord.Embed(title="Bot Functionality Guide", color=int(EMBED_COLOR.lstrip('#'), 16))

    helpMessage = """ 
1. **/createjob** - Allows an admin to create a new job by providing a date, time, location, and optional details.
2. **/editjob** - Allows an admin to edit an existing job's details (time, location, or details).
3. **/viewjobs** - Displays a paginated list of active jobs. Users can navigate between pages using reactions (◀️ and ▶️).
"""
    embed.description = helpMessage
    await interaction.response.send_message(embed=embed)

# Start the bot
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    
    # Await the sync operation
    await bot.tree.sync()
    
    # Now you can print the number of commands after syncing
    commands = bot.tree.get_commands()
    print(f"Synced {len(commands)} commands")
    print("Bot is ready and commands are synced.")

bot.run(TOKEN)