import os
import discord
from discord import app_commands
import random
import string
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
from prisma import Prisma

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

prisma = Prisma()


class MyClient(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.prisma = prisma

    async def setup_hook(self):
        await self.tree.sync()
        await self.prisma.connect()
        self.bg_task = self.loop.create_task(check_team_expiration())


client = MyClient()

VALORANT_RANKS = ["Iron", "Bronze", "Silver", "Platinum", "Gold", "Diamond", "Ascendant", "Immortal", "Radiant"]


class PersistentTeamButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Приєднатися", style=discord.ButtonStyle.green, custom_id="join_team")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await join_team(interaction, interaction.message.embeds[0].title.split()[-1])

    @discord.ui.button(label="Покинути", style=discord.ButtonStyle.red, custom_id="leave_team")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await leave_team(interaction, interaction.message.embeds[0].title.split()[-1])

    @discord.ui.button(label="Розпустити", style=discord.ButtonStyle.grey, custom_id="disband_team")
    async def disband_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await disband_team(interaction, interaction.message.embeds[0].title.split()[-1])


def generate_team_id():
    team_id = ''.join(random.choices(string.digits, k=5))
    return team_id


async def create_team_embed(team_id):
    team = await client.prisma.team.find_unique(
        where={'id': team_id},
        include={'players': True}
    )
    if not team or team.status != 'active':
        return None, None

    embed = discord.Embed(title=f"🎮 Команда {team_id}", color=0x00ff00)
    player_list = []
    for player in team.players:
        if player.status == 'active':
            member = client.get_guild(int(team.guildId)).get_member(int(player.id))
            if member:
                valorant_roles = [role.name for role in member.roles if role.name in VALORANT_RANKS]
                role_str = f" ({', '.join(valorant_roles)})" if valorant_roles else ""
                emoji = "👑" if player.id == team.leaderId else "👤"
                player_list.append(f"{emoji} {member.mention}{role_str}")

    while len(player_list) < 5:
        player_list.append("🔓 Вільне місце")

    embed.add_field(name="👥 Гравці:", value="\n".join(player_list) or "Немає гравців", inline=False)

    reserve_list = [f"🔹 {client.get_guild(int(team.guildId)).get_member(int(player.id)).mention}" for player in
                    team.players if player.isReserve and player.status == 'active']
    if reserve_list:
        embed.add_field(name="🔄 Резерв:", value="\n".join(reserve_list), inline=False)

    embed.add_field(name="🕒 Створено:", value=team.createdAt.strftime("%Y-%m-%d %H:%M:%S"), inline=False)

    if len([p for p in team.players if not p.isReserve and p.status == 'active']) == 5:
        embed.add_field(name="✅ Статус:", value="Команда повна! 🎉", inline=False)

    embed.set_footer(
        text=f"🆓 Вільних місць: {5 - len([p for p in team.players if not p.isReserve and p.status == 'active'])}")
    return embed, PersistentTeamButtons()


async def update_team_message(team_id):
    team = await client.prisma.team.find_unique(
        where={'id': team_id},
        include={'players': True}
    )
    if not team or team.status != 'active':
        return

    embed, view = await create_team_embed(team_id)
    if embed and view:
        channel = client.get_channel(int(team.channelId))
        message = await channel.fetch_message(int(team.messageId))
        await message.edit(content="", embed=embed, view=view)


async def is_user_in_team(user_id):
    player = await client.prisma.player.find_first(
        where={
            'id': str(user_id),
            'status': 'active',
            'team': {
                'is_not': None,
                'status': 'active'
            }
        }
    )
    return player is not None


async def get_user_team(user_id):
    player = await client.prisma.player.find_first(
        where={
            'id': str(user_id),
            'status': 'active',
            'team': {
                'is_not': None,
                'status': 'active'
            }
        },
        include={'team': True}
    )
    return player.team.id if player else None


async def disband_team(interaction: discord.Interaction, team_id: str, expired: bool = False):
    team = await client.prisma.team.find_unique(
        where={'id': team_id},
        include={'players': True}
    )
    if not team or team.status != 'active':
        if interaction:
            await interaction.response.send_message("❌ Команда не існує або вже розпущена.", ephemeral=True)
        return

    if interaction and str(interaction.user.id) != team.leaderId:
        await interaction.response.send_message("❌ Ви не є лідером цієї команди.", ephemeral=True)
        return

    # Обновляем статус команды
    await client.prisma.team.update(
        where={'id': team_id},
        data={'status': 'disbanded'}
    )

    # Обновляем статус всех игроков команды
    for player in team.players:
        await client.prisma.player.update(
            where={'id': player.id},
            data={'status': 'inactive'}
        )

    # Удаляем сообщение команды из Discord
    channel = client.get_channel(int(team.channelId))
    try:
        message = await channel.fetch_message(int(team.messageId))
        await message.delete()
    except discord.errors.NotFound:
        print(f"Повідомлення для команди {team_id} не знайдено.")
    except Exception as e:
        print(f"Помилка при видаленні повідомлення для команди {team_id}: {e}")

    if interaction:
        await interaction.response.send_message(f"🚫 Команда {team_id} розпущена.", ephemeral=True)
    elif expired:
        try:
            await channel.send(f"🕒 Команда {team_id} була автоматично розпущена через неактивність.")
        except Exception as e:
            print(f"Помилка при відправці повідомлення про роспуск команди {team_id}: {e}")


@client.event
async def on_ready():
    print(f'{client.user} підключився до Discord!')
    try:
        synced = await client.tree.sync()
        print(f"Синхронізовано {len(synced)} команд")

        # Восстановление кнопок для существующих активных команд
        active_teams = await client.prisma.team.find_many(
            where={'status': 'active'}
        )
        for team in active_teams:
            channel = client.get_channel(int(team.channelId))
            if channel:
                try:
                    message = await channel.fetch_message(int(team.messageId))
                    await message.edit(view=PersistentTeamButtons())
                except discord.errors.NotFound:
                    print(f"Повідомлення для команди {team.id} не знайдено.")
                except Exception as e:
                    print(f"Помилка при оновленні повідомлення для команди {team.id}: {e}")

    except Exception as e:
        print(f"Помилка при синхронізації команд: {e}")


async def check_team_expiration():
    while True:
        now = datetime.now()
        expired_teams = await client.prisma.team.find_many(
            where={
                'createdAt': {
                    'lt': now - timedelta(hours=6)
                },
                'status': 'active'
            }
        )
        for team in expired_teams:
            await disband_team(None, team.id, expired=True)
        await asyncio.sleep(60)


@client.tree.command(name="help", description="Показати довідку по командам бота")
async def help_command(interaction: discord.Interaction):
    with open('help_text.txt', 'r', encoding='utf-8') as file:
        help_text = file.read()

    embed = discord.Embed(title="Довідка по командам бота", description=help_text, color=0x00ff00)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@client.tree.command(name="create", description="Створити нову команду")
async def create(interaction: discord.Interaction):
    if await is_user_in_team(interaction.user.id):
        await interaction.response.send_message("❌ Ви вже є учасником команди. Ви не можете створити нову.",
                                                ephemeral=True)
        return

    team_id = generate_team_id()

    try:
        team = await client.prisma.team.create({
            'data': {
                'id': team_id,
                'leaderId': str(interaction.user.id),
                'channelId': str(interaction.channel.id),
                'guildId': str(interaction.guild.id),
                'messageId': '0',  # Временное значение, обновим позже
                'status': 'active',
                'players': {
                    'create': {
                        'id': str(interaction.user.id),
                        'status': 'active'
                    }
                }
            }
        })

        embed, view = await create_team_embed(team_id)
        if embed and view:
            await interaction.response.send_message(
                f"🎉 Гравець {interaction.user.mention} створив команду! {interaction.guild.default_role.mention}\n@everyone",
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(everyone=True)
            )

            message = await interaction.original_response()
            await client.prisma.team.update(
                where={'id': team_id},
                data={'messageId': str(message.id)}
            )

            await update_team_message(team_id)
        else:
            await interaction.response.send_message(
                "❌ Виникла помилка при створенні команди. Будь ласка, спробуйте ще раз пізніше.", ephemeral=True)
    except Exception as e:
        print(f"Error creating team: {e}")
        await interaction.response.send_message(
            "❌ Виникла помилка при створенні команди. Будь ласка, спробуйте ще раз пізніше.", ephemeral=True)


async def join_team(interaction: discord.Interaction, team_id: str):
    if await is_user_in_team(interaction.user.id):
        await interaction.response.send_message("❌ Ви вже є учасником команди. Ви не можете приєднатися до іншої.",
                                                ephemeral=True)
        return

    team = await client.prisma.team.find_unique(
        where={'id': team_id},
        include={'players': True}
    )
    if not team or team.status != 'active':
        await interaction.response.send_message("❌ Команда з таким ID не існує або неактивна.", ephemeral=True)
        return

    if any(player.id == str(interaction.user.id) and player.status == 'active' for player in team.players):
        await interaction.response.send_message("❌ Ви вже в цій команді.", ephemeral=True)
        return

    active_players = [p for p in team.players if not p.isReserve and p.status == 'active']
    if len(active_players) >= 5:
        if len([p for p in team.players if p.isReserve and p.status == 'active']) < 2:
            try:
                await client.prisma.player.create(
                    data={
                        'id': str(interaction.user.id),
                        'teamId': team_id,
                        'isReserve': True,
                        'status': 'active'
                    }
                )
                await update_team_message(team_id)
                await interaction.response.send_message("✅ Ви додані до резерву команди.", ephemeral=True)
            except Exception as e:
                print(f"Error adding player to reserve: {e}")
                await interaction.response.send_message(
                    "❌ Виникла помилка при додаванні вас до резерву. Будь ласка, спробуйте ще раз пізніше.",
                    ephemeral=True)
        else:
            await interaction.response.send_message("❌ Команда та резерв вже повні.", ephemeral=True)
        return

    try:
        await client.prisma.player.create(
            data={
                'id': str(interaction.user.id),
                'teamId': team_id,
                'isReserve': False,
                'status': 'active'
            }
        )
        await update_team_message(team_id)
        await interaction.response.send_message("✅ Ви успішно приєдналися до команди.", ephemeral=True)
    except Exception as e:
        print(f"Error adding player to team: {e}")
        await interaction.response.send_message(
            "❌ Виникла помилка при приєднанні до команди. Будь ласка, спробуйте ще раз пізніше.", ephemeral=True)


async def leave_team(interaction: discord.Interaction, team_id: str):
    team = await client.prisma.team.find_unique(
        where={'id': team_id},
        include={'players': True}
    )
    if not team or team.status != 'active' or not any(
            player.id == str(interaction.user.id) and player.status == 'active' for player in team.players):
        await interaction.response.send_message("❌ Ви не є учасником цієї команди.", ephemeral=True)
        return

    player = next(
        player for player in team.players if player.id == str(interaction.user.id) and player.status == 'active')

    if player.isReserve:
        await client.prisma.player.update(
            where={'id': str(interaction.user.id)},
            data={'status': 'inactive'}
        )
        await update_team_message(team_id)
        await interaction.response.send_message("✅ Ви успішно покинули резерв команди.", ephemeral=True)
        return

    if str(interaction.user.id) == team.leaderId:
        active_players = [p for p in team.players if
                          not p.isReserve and p.status == 'active' and p.id != str(interaction.user.id)]
        if active_players:
            new_leader = random.choice(active_players)
            await client.prisma.team.update(
                where={'id': team_id},
                data={'leaderId': new_leader.id}
            )
            await client.prisma.player.update(
                where={'id': str(interaction.user.id)},
                data={'status': 'inactive'}
            )
            reserve_players = [p for p in team.players if p.isReserve and p.status == 'active']
            if reserve_players:
                new_active_player = reserve_players[0]
                await client.prisma.player.update(
                    where={'id': new_active_player.id},
                    data={'isReserve': False}
                )
            await update_team_message(team_id)
            await interaction.response.send_message("✅ Ви успішно покинули команду.", ephemeral=True)

        async def disband_team(interaction: discord.Interaction, team_id: str, expired: bool = False):
            team = await client.prisma.team.find_unique(
                where={'id': team_id},
                include={'players': True}
            )
            if not team or team.status != 'active':
                if interaction:
                    await interaction.response.send_message("❌ Команда не існує або вже розпущена.", ephemeral=True)
                return

            if interaction and str(interaction.user.id) != team.leaderId:
                await interaction.response.send_message("❌ Ви не є лідером цієї команди.", ephemeral=True)
                return

            # Обновляем статус команды
            await client.prisma.team.update(
                where={'id': team_id},
                data={'status': 'disbanded'}
            )

            # Обновляем статус всех игроков команды
            for player in team.players:
                await client.prisma.player.update(
                    where={'id': player.id},
                    data={'status': 'inactive'}
                )

            # Удаляем сообщение команды из Discord
            channel = client.get_channel(int(team.channelId))
            try:
                message = await channel.fetch_message(int(team.messageId))
                await message.delete()
            except discord.errors.NotFound:
                print(f"Повідомлення для команди {team_id} не знайдено.")
            except Exception as e:
                print(f"Помилка при видаленні повідомлення для команди {team_id}: {e}")

            if interaction:
                await interaction.response.send_message(f"🚫 Команда {team_id} розпущена.", ephemeral=True)
            elif expired:
                try:
                    await channel.send(f"🕒 Команда {team_id} була автоматично розпущена через неактивність.")
                except Exception as e:
                    print(f"Помилка при відправці повідомлення про роспуск команди {team_id}: {e}")

        @client.tree.command(name="invite", description="Запросити гравця до команди")
        async def invite(interaction: discord.Interaction, player: discord.Member):
            team_id = await get_user_team(interaction.user.id)
            if not team_id:
                await interaction.response.send_message("❌ Ви не є лідером жодної команди.", ephemeral=True)
                return

            team = await client.prisma.team.find_unique(
                where={'id': team_id},
                include={'players': True}
            )

            if str(interaction.user.id) != team.leaderId:
                await interaction.response.send_message("❌ Тільки лідер команди може запрошувати гравців.",
                                                        ephemeral=True)
                return

            if await is_user_in_team(player.id):
                await interaction.response.send_message(f"❌ Гравець {player.mention} вже є учасником іншої команди.",
                                                        ephemeral=True)
                return

            active_players = [p for p in team.players if not p.isReserve and p.status == 'active']
            if len(active_players) >= 5:
                if len([p for p in team.players if p.isReserve and p.status == 'active']) < 2:
                    try:
                        await client.prisma.player.create(
                            data={
                                'id': str(player.id),
                                'teamId': team_id,
                                'isReserve': True,
                                'status': 'active'
                            }
                        )
                        await update_team_message(team_id)
                        await interaction.response.send_message(
                            f"✅ Гравець {player.mention} доданий до резерву команди.", ephemeral=True)
                    except Exception as e:
                        print(f"Error adding player to reserve: {e}")
                        await interaction.response.send_message(
                            "❌ Виникла помилка при додаванні гравця до резерву. Будь ласка, спробуйте ще раз пізніше.",
                            ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Команда та резерв вже повні.", ephemeral=True)
                return

            try:
                await client.prisma.player.create(
                    data={
                        'id': str(player.id),
                        'teamId': team_id,
                        'isReserve': False,
                        'status': 'active'
                    }
                )
                await update_team_message(team_id)
                await interaction.response.send_message(f"✅ Гравець {player.mention} доданий до команди.",
                                                        ephemeral=True)
            except Exception as e:
                print(f"Error adding player to team: {e}")
                await interaction.response.send_message(
                    "❌ Виникла помилка при додаванні гравця до команди. Будь ласка, спробуйте ще раз пізніше.",
                    ephemeral=True)

        client.run(os.getenv('DISCORD_TOKEN'))
