import os
import discord
from discord import app_commands
import random
import string
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        self.bg_task = self.loop.create_task(check_team_expiration())

client = MyClient()
teams = {}

VALORANT_RANKS = ["Iron", "Bronze", "Silver", "Platinum", "Gold", "Diamond", "Ascendant", "Immortal", "Radiant"]

class JoinButton(discord.ui.Button):
    def __init__(self, team_id: str):
        super().__init__(style=discord.ButtonStyle.green, label="Приєднатися")
        self.team_id = team_id

    async def callback(self, interaction: discord.Interaction):
        await join_team(interaction, self.team_id)

class LeaveButton(discord.ui.Button):
    def __init__(self, team_id: str):
        super().__init__(style=discord.ButtonStyle.red, label="Покинути")
        self.team_id = team_id

    async def callback(self, interaction: discord.Interaction):
        await leave_team(interaction, self.team_id)

class DisbandButton(discord.ui.Button):
    def __init__(self, team_id: str):
        super().__init__(style=discord.ButtonStyle.grey, label="Розпустити")
        self.team_id = team_id

    async def callback(self, interaction: discord.Interaction):
        await disband_team(interaction, self.team_id)

class TeamButtons(discord.ui.View):
    def __init__(self, team_id: str):
        super().__init__(timeout=None)
        self.team_id = team_id
        self.add_item(JoinButton(team_id))
        self.add_item(LeaveButton(team_id))
        self.add_item(DisbandButton(team_id))

    def update_join_button(self, team):
        # Update Join button label based on team capacity
        join_button = discord.utils.get(self.children, label="Приєднатися") or discord.utils.get(self.children, label="Черга")
        if join_button:
            if len([p for p in team['players'] if p]) >= 5:
                join_button.label = "Черга"
            else:
                join_button.label = "Приєднатися"

def generate_team_id():
    # Generate a random 5-digit team ID
    return ''.join(random.choices(string.digits, k=5))

def create_team_embed(team_id):
    # Create an embed with team information
    team = teams.get(team_id, {})
    embed = discord.Embed(title=f"🎮 Команда {team_id}", color=0x00ff00)
    player_list = []
    for player in team.get('players', []):
        if player:
            valorant_roles = [role.name for role in player.roles if role.name in VALORANT_RANKS]
            role_str = f" ({', '.join(valorant_roles)})" if valorant_roles else ""
            emoji = "👑" if player == team['leader'] else "👤"
            player_list.append(f"{emoji} {player.mention}{role_str}")
        else:
            player_list.append("🔓 Вільне місце")
    embed.add_field(name="👥 Гравці:", value="\n".join(player_list) or "Немає гравців", inline=False)

    reserve_list = [f"🔹 {player.mention}" for player in team.get('reserve', [])]
    if reserve_list:
        embed.add_field(name="🔄 Резерв:", value="\n".join(reserve_list), inline=False)

    embed.add_field(name="🕒 Створено:", value=team.get('created_at', datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), inline=False)

    if len([p for p in team.get('players', []) if p]) == 5:
        embed.add_field(name="✅ Статус:", value="Команда повна! 🎉", inline=False)

    embed.set_footer(text=f"🆓 Вільних місць: {5 - len([p for p in team.get('players', []) if p])}")
    return embed

async def update_team_message(team_id):
    # Update the team message with current information
    team = teams[team_id]
    guild = client.get_guild(team['guild_id'])
    if guild:
        for i, player in enumerate(team['players']):
            if player:
                member = guild.get_member(player.id)
                if member:
                    team['players'][i] = member
    embed = create_team_embed(team_id)
    channel = client.get_channel(team['channel_id'])
    message = await channel.fetch_message(team['message_id'])
    view = TeamButtons(team_id)
    view.update_join_button(team)
    await message.edit(content="", embed=embed, view=view)

def is_user_in_team(user):
    # Check if a user is already in a team
    for team in teams.values():
        if any(player and player.id == user.id for player in team['players']):
            return True
    return False

def get_user_team(user):
    # Get the team ID for a given user
    for team_id, team in teams.items():
        if any(player and player.id == user.id for player in team['players']):
            return team_id
    return None

@client.event
async def on_ready():
    print(f'{client.user} підключився до Discord!')
    try:
        synced = await client.tree.sync()
        print(f"Синхронізовано {len(synced)} команд")
    except Exception as e:
        print(e)

async def check_team_expiration():
    # Check and delete expired teams every minute
    while True:
        now = datetime.now()
        for team_id, team in list(teams.items()):
            if now - team['created_at'] > timedelta(hours=6):
                await delete_team(team_id)
        await asyncio.sleep(60)

async def delete_team(team_id):
    # Delete a team and its message
    team = teams[team_id]
    channel = client.get_channel(team['channel_id'])
    try:
        message = await channel.fetch_message(team['message_id'])
        await message.delete()
    except:
        pass  # Message might have been already deleted
    del teams[team_id]

@client.tree.command(name="help", description="Показати довідку по командам бота")
async def help_command(interaction: discord.Interaction):
    # Display help information
    with open('help_text.txt', 'r', encoding='utf-8') as file:
        help_text = file.read()

    embed = discord.Embed(title="Довідка по командам бота", description=help_text, color=0x00ff00)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@client.tree.command(name="create", description="Створити нову команду")
async def create(interaction: discord.Interaction):
    # Create a new team
    if is_user_in_team(interaction.user):
        await interaction.response.send_message("❌ Ви вже є учасником команди. Ви не можете створити нову.", ephemeral=True)
        return

    team_id = generate_team_id()

    teams[team_id] = {
        'players': [interaction.user] + [None] * 4,
        'leader': interaction.user,
        'created_at': datetime.now(),
        'channel_id': interaction.channel.id,
        'guild_id': interaction.guild.id,
        'reserve': []
    }

    embed = create_team_embed(team_id)
    view = TeamButtons(team_id)

    await interaction.response.send_message(
        f"🎉 Гравець {interaction.user.mention} створив команду! {interaction.guild.default_role.mention}\n@everyone",
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(everyone=True)
    )

    message = await interaction.original_response()
    teams[team_id]['message_id'] = message.id

    await update_team_message(team_id)

async def join_team(interaction: discord.Interaction, team_id: str):
    # Join a team or queue if full
    if is_user_in_team(interaction.user):
        await interaction.response.send_message("❌ Ви вже є учасником команди. Ви не можете приєднатися до іншої.", ephemeral=True)
        return

    team = teams.get(team_id)
    if not team:
        await interaction.response.send_message("❌ Команда з таким ID не існує.", ephemeral=True)
        return

    if interaction.user in team['players']:
        await interaction.response.send_message("❌ Ви вже в цій команді.", ephemeral=True)
        return

    if None not in team['players']:
        if len(team['reserve']) < 2:
            team['reserve'].append(interaction.user)
            await update_team_message(team_id)
            await interaction.response.send_message("✅ Ви додані до резерву команди.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Команда та резерв вже повні.", ephemeral=True)
        return

    team['players'][team['players'].index(None)] = interaction.user
    await update_team_message(team_id)
    await interaction.response.send_message("✅ Ви успішно приєдналися до команди.", ephemeral=True)

async def leave_team(interaction: discord.Interaction, team_id: str):
    # Leave a team
    team = teams.get(team_id)
    if not team or (interaction.user not in team['players'] and interaction.user not in team['reserve']):
        await interaction.response.send_message("❌ Ви не є учасником цієї команди.", ephemeral=True)
        return

    if interaction.user in team['reserve']:
        team['reserve'].remove(interaction.user)
        await update_team_message(team_id)
        await interaction.response.send_message("✅ Ви успішно покинули резерв команди.", ephemeral=True)
        return

    if interaction.user == team['leader']:
        # Handle leader leaving
        active_players = [p for p in team['players'] if p and p != interaction.user]
        if active_players:
            new_leader = random.choice(active_players)
            team['leader'] = new_leader
            team['players'][team['players'].index(interaction.user)] = None
            if team['reserve']:
                new_player = team['reserve'].pop(0)
                team['players'][team['players'].index(None)] = new_player
                await new_player.send(f"✅ Ви були переміщені з резерву до активного складу команди {team_id}!")
            await update_team_message(team_id)
            await interaction.response.send_message(f"✅ Ви успішно покинули команду. Новим лідером став {new_leader.mention}.", ephemeral=True)
        else:
            await disband_team(interaction, team_id)
    else:
        # Handle regular player leaving
        team['players'][team['players'].index(interaction.user)] = None
        if team['reserve']:
            new_player = team['reserve'].pop(0)
            team['players'][team['players'].index(None)] = new_player
            await new_player.send(f"✅ Ви були переміщені з резерву до активного складу команди {team_id}!")
        await update_team_message(team_id)
        await interaction.response.send_message("✅ Ви успішно покинули команду.", ephemeral=True)

async def disband_team(interaction: discord.Interaction, team_id: str):
    # Disband a team
    team = teams.get(team_id)
    if not team or interaction.user != team['leader']:
        await interaction.response.send_message("❌ Ви не є лідером цієї команди.", ephemeral=True)
        return

    await delete_team(team_id)
    await interaction.response.send_message(f"🚫 Команда {team_id} розпущена.", ephemeral=True)

@client.tree.command(name="invite", description="Запросити гравця до команди")
async def invite(interaction: discord.Interaction, player: discord.Member):
    # Invite a player to the team
    team_id = get_user_team(interaction.user)
    if not team_id:
        await interaction.response.send_message("❌ Ви не є лідером жодної команди.", ephemeral=True)
        return

    team = teams[team_id]

    if interaction.user != team['leader']:
        await interaction.response.send_message("❌ Тільки лідер команди може запрошувати гравців.", ephemeral=True)
        return

    if is_user_in_team(player):
        await interaction.response.send_message(f"❌ Гравець {player.mention} вже є учасником іншої команди.", ephemeral=True)
        return

    if None not in team['players']:
        if len(team['reserve']) < 2:
            team['reserve'].append(player)
            await update_team_message(team_id)
            await interaction.response.send_message(f"✅ Гравець {player.mention} доданий до резерву команди.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Команда та резерв вже повні.", ephemeral=True)
        return

    team['players'][team['players'].index(None)] = player
    await update_team_message(team_id)
    await interaction.response.send_message(f"✅ Гравець {player.mention} доданий до команди.", ephemeral=True)

client.run(os.getenv('DISCORD_TOKEN'))