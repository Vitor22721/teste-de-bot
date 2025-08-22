import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import json
import os
import random
import asyncio
from collections import deque
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import requests
import youtube_dl
import math

# ================== CONFIGURAÇÕES BÁSICAS ==================
RAID_LIMITE = 5
RAID_INTERVALO = 10
entradas_recent = deque()
ID_DO_CANAL_DE_ALERTA = 1396668435794104481

class MeuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="&", intents=intents)

        # Inicialização de variáveis do bot
        self.playlist = []
        self.current_song = None
        self.voice_client = None
        self.radio_playing = False

    async def setup_hook(self):
        self.loop.create_task(trocar_loja_periodicamente())
        self.loop.create_task(evento_sazonal_check())
        self.loop.create_task(radio_24_7())
        atualizar_atividade.start()

bot = MeuBot()
bot.remove_command("help")

# ================== CANAIS AUTORIZADOS ==================
CANAL_AUTORIZADO = [
    1390745745191211019, 1396696858474319974, 1396697270011039875,
    1396698291223269428, 1396717788764311592, 1396935060338512002,
    1396992790184857620, 1381270223784771705, 1390745745191211019,
    1396242664944439376, 1396232612841783316
]

SERVIDORES_BLOQUEADOS = [1191397056116437143]

# Canais específicos
CANAL_SALDO = 1396696858474319974
CANAL_INVESTIR = 1396697270011039875
CANAL_TRABALHO = 1396698291223269428
CANAL_TRANSACOES = 1396717788764311592
CANAL_LOJA = 1396935060338512002
CANAL_LOTERIA = 1396992790184857620

CANAL_MUSICA = 1386671492493873242
CANAL_JOGOS = 1390745745191211019
CANAL_STATS = 1390745745191211019

# ================== ARQUIVOS DE DADOS ==================
MOEDA_FILE = "dinheiro.json"
INVEST_FILE = "investimentos.json"
LOJA_STATUS_FILE = "loja_status.json"
BLACKLIST_FILE = "blacklist.json"
WARN_FILE = "warns.json"
LOTERIA_FILE = "loteria.json"
XP_FILE = "xp.json"
CRYPTO_FILE = "crypto.json"
RPG_FILE = "rpg.json"
ATIVIDADE_FILE = "atividade.json"
EVENTOS_FILE = "eventos.json"

ALLOWED_USERS = [561565693355753474, 969521624271425556, 717873758945411132]

# ================== FUNÇÕES AUXILIARES ==================
def is_allowed(ctx):
    return ctx.author.id in ALLOWED_USERS

def load_json(file):
    if os.path.exists(file):
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_loteria():
    if os.path.exists(LOTERIA_FILE):
        with open(LOTERIA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"acumulado": 0, "numeros": {}, "historico": []}

def save_loteria(data):
    with open(LOTERIA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ================== CARREGAMENTO DE DADOS ==================
money = load_json(MOEDA_FILE)
investments = load_json(INVEST_FILE)
blacklist = load_json(BLACKLIST_FILE)
warns_data = load_json(WARN_FILE)
loteria = load_loteria()
xp_data = load_json(XP_FILE)
crypto_data = load_json(CRYPTO_FILE)
rpg_data = load_json(RPG_FILE)
atividade_data = load_json(ATIVIDADE_FILE)
eventos_data = load_json(EVENTOS_FILE)

# Inicializar dados de crypto se não existir
if not crypto_data:
    crypto_data = {
        "bitcoin": {"preco": 50000, "historico": []},
        "ethereum": {"preco": 3000, "historico": []},
        "replitcoin": {"preco": 100, "historico": []}
    }
    save_json(CRYPTO_FILE, crypto_data)

# ================== SISTEMA DE XP ==================
def get_xp(user_id):
    return xp_data.get(str(user_id), {"xp": 0, "nivel": 1})

def add_xp(user_id, xp_ganho):
    user_str = str(user_id)
    if user_str not in xp_data:
        xp_data[user_str] = {"xp": 0, "nivel": 1}

    xp_data[user_str]["xp"] += xp_ganho
    nivel_anterior = xp_data[user_str]["nivel"]
    novo_nivel = int(xp_data[user_str]["xp"] ** 0.5 / 10) + 1

    if novo_nivel > nivel_anterior:
        xp_data[user_str]["nivel"] = novo_nivel
        save_json(XP_FILE, xp_data)
        return novo_nivel

    save_json(XP_FILE, xp_data)
    return None

# ================== SISTEMA DE ATIVIDADE ==================
def registrar_atividade(user_id, acao):
    hoje = datetime.now().strftime("%Y-%m-%d")
    user_str = str(user_id)

    if hoje not in atividade_data:
        atividade_data[hoje] = {}

    if user_str not in atividade_data[hoje]:
        atividade_data[hoje][user_str] = {"mensagens": 0, "comandos": 0, "tempo_ativo": 0}

    atividade_data[hoje][user_str][acao] += 1
    save_json(ATIVIDADE_FILE, atividade_data)

@tasks.loop(hours=1)
async def atualizar_atividade():
    # Limpa dados antigos (mais de 30 dias)
    cutoff = datetime.now() - timedelta(days=30)
    keys_to_remove = []

    for date_str in atividade_data:
        if datetime.strptime(date_str, "%Y-%m-%d") < cutoff:
            keys_to_remove.append(date_str)

    for key in keys_to_remove:
        del atividade_data[key]

    save_json(ATIVIDADE_FILE, atividade_data)

# ================== SISTEMA DE EVENTOS SAZONAIS ==================
eventos_sazonais = {
    "halloween": {
        "inicio": "10-01",
        "fim": "11-07",
        "bonus_trabalho": 2.0,
        "itens_especiais": ["🎃 Abóbora Dourada", "👻 Fantasma Amigável"],
        "mensagem": "🎃 **EVENTO HALLOWEEN ATIVO!** Ganhos em dobro!"
    },
    "natal": {
        "inicio": "12-15",
        "fim": "01-07",
        "bonus_trabalho": 1.5,
        "itens_especiais": ["🎁 Presente Especial", "🎅 Gorro Mágico"],
        "mensagem": "🎄 **EVENTO NATAL ATIVO!** Ho ho ho!"
    },
    "ano_novo": {
        "inicio": "12-31",
        "fim": "01-03",
        "bonus_trabalho": 3.0,
        "itens_especiais": ["🎆 Fogos Mágicos"],
        "mensagem": "🎆 **ANO NOVO!** Ganhos triplicados!"
    }
}

def evento_ativo():
    agora = datetime.now()
    mes_dia = agora.strftime("%m-%d")

    for nome, evento in eventos_sazonais.items():
        inicio = evento["inicio"]
        fim = evento["fim"]

        if inicio <= fim:
            if inicio <= mes_dia <= fim:
                return evento
        else:  # Evento que cruza o ano (ex: natal)
            if mes_dia >= inicio or mes_dia <= fim:
                return evento

    return None

@tasks.loop(hours=6)
async def evento_sazonal_check():
    evento = evento_ativo()
    if evento:
        canal = bot.get_channel(ID_DO_CANAL_DE_ALERTA)
        if canal:
            await canal.send(evento["mensagem"])

# ================== SISTEMA DE MÚSICA ==================
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# ================== SISTEMA DE RPG ==================
classes_rpg = {
    "guerreiro": {"vida": 120, "ataque": 25, "defesa": 20, "agilidade": 10},
    "mago": {"vida": 80, "ataque": 35, "defesa": 10, "agilidade": 15},
    "ladino": {"vida": 100, "ataque": 20, "defesa": 15, "agilidade": 25}
}

def get_rpg_player(user_id):
    user_str = str(user_id)
    if user_str not in rpg_data:
        return None
    return rpg_data[user_str]

def criar_personagem(user_id, classe, nome):
    user_str = str(user_id)
    stats = classes_rpg[classe].copy()
    rpg_data[user_str] = {
        "nome": nome,
        "classe": classe,
        "nivel": 1,
        "vida_max": stats["vida"],
        "vida_atual": stats["vida"],
        "ataque": stats["ataque"],
        "defesa": stats["defesa"],
        "agilidade": stats["agilidade"],
        "xp": 0,
        "gold": 100,
        "inventario": [],
        "equipamentos": {}
    }
    save_json(RPG_FILE, rpg_data)

# ================== SISTEMA DE CRIPTOMOEDAS ==================
def atualizar_precos_crypto():
    for crypto in crypto_data:
        variacao = random.uniform(-0.15, 0.15)  # -15% a +15%
        novo_preco = max(1, int(crypto_data[crypto]["preco"] * (1 + variacao)))
        crypto_data[crypto]["preco"] = novo_preco

        # Manter histórico dos últimos 24 pontos
        if len(crypto_data[crypto]["historico"]) >= 24:
            crypto_data[crypto]["historico"].pop(0)
        crypto_data[crypto]["historico"].append(novo_preco)

    save_json(CRYPTO_FILE, crypto_data)

# ================== RÁDIO 24/7 ==================
radio_urls = [
    "https://www.youtube.com/watch?v=jfKfPfyJRdk",  # Lofi
    "https://www.youtube.com/watch?v=5qap5aO4i9A",  # Chill
    "https://www.youtube.com/watch?v=DWcJFNfaw9c"   # Study music
]

async def radio_24_7():
    await bot.wait_until_ready()
    while not bot.is_closed():
        if bot.radio_playing and bot.voice_client:
            if not bot.voice_client.is_playing():
                try:
                    url = random.choice(radio_urls)
                    player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
                    bot.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
                except Exception as e:
                    print(f"Erro na rádio: {e}")

        await asyncio.sleep(300)  # Verifica a cada 5 minutos

# ================== DECORADORES ==================
def apenas_no_canal(canal_id):
    async def predicate(ctx):
        if ctx.channel.id != canal_id:
            await ctx.send(f"❌ Este comando só pode ser usado em <#{canal_id}>!")
            return False
        return True
    return commands.check(predicate)

# ================== SISTEMA DE WARNS ==================
def limpar_warns_antigos(user_id):
    agora = datetime.now()
    user_id_str = str(user_id)
    if user_id_str not in warns_data:
        return

    novos_warns = []
    for warn in warns_data[user_id_str]:
        if agora - datetime.fromisoformat(warn["data"]) <= timedelta(days=30):
            novos_warns.append(warn)

    warns_data[user_id_str] = novos_warns
    if not novos_warns:
        warns_data.pop(user_id_str, None)

    save_json(WARN_FILE, warns_data)

def get_warns_count(user_id):
    limpar_warns_antigos(user_id)
    return len(warns_data.get(str(user_id), []))

def set_warns(user_id, quantidade):
    user_id_str = str(user_id)
    if quantidade <= 0:
        warns_data.pop(user_id_str, None)
    else:
        warns_data[user_id_str] = [{
            "moderador": "Sistema",
            "motivo": "Ajuste manual",
            "data": datetime.now().isoformat()
        } for _ in range(quantidade)]
    save_json(WARN_FILE, warns_data)

# ================== SISTEMA ECONÔMICO ==================
def get_saldo(user_id):
    return money.get(str(user_id), 1000)

def set_saldo(user_id, valor):
    money[str(user_id)] = valor
    save_json(MOEDA_FILE, money)

# ================== EVENTOS DO BOT ==================
@bot.event
async def on_ready():
    print(f"{bot.user} está online!")
    atualizar_precos_crypto()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Sistema de XP
    xp_ganho = random.randint(5, 15)
    novo_nivel = add_xp(message.author.id, xp_ganho)
    if novo_nivel:
        await message.channel.send(f"🎉 {message.author.mention} subiu para o nível **{novo_nivel}**!")

    # Registrar atividade
    registrar_atividade(message.author.id, "mensagens")

    await bot.process_commands(message)

@bot.event
async def on_command(ctx):
    registrar_atividade(ctx.author.id, "comandos")

@bot.event
async def on_member_join(member):
    agora = datetime.now()
    entradas_recent.append(agora)
    while entradas_recent and (agora - entradas_recent[0]).total_seconds() > RAID_INTERVALO:
        entradas_recent.popleft()

    if len(entradas_recent) > RAID_LIMITE:
        canal_alerta = bot.get_channel(ID_DO_CANAL_DE_ALERTA)
        if canal_alerta:
            await canal_alerta.send(f"🚨 **POSSÍVEL RAID DETECTADO!** Mais de {RAID_LIMITE} membros entraram em {RAID_INTERVALO} segundos.")

        try:
            await member.ban(reason="Suspeita de raid")
        except Exception as e:
            print(f"Erro ao banir membro: {e}")

# ================== COMANDOS DE MÚSICA ==================
@bot.command()
@apenas_no_canal(CANAL_MUSICA)
async def play(ctx, *, url):
    """Toca uma música do YouTube"""
    if not ctx.author.voice:
        return await ctx.send("❌ Você precisa estar em um canal de voz!")

    channel = ctx.author.voice.channel

    if not bot.voice_client:
        bot.voice_client = await channel.connect()

    try:
        async with ctx.typing():
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            bot.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
            bot.current_song = player

        embed = discord.Embed(title="🎵 Tocando agora", description=f"**{player.title}**", color=discord.Color.green())
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Erro ao tocar música: {str(e)}")

@bot.command()
@apenas_no_canal(CANAL_MUSICA)
async def queue(ctx, *, url):
    """Adiciona uma música à playlist"""
    bot.playlist.append(url)
    await ctx.send(f"🎵 Música adicionada à playlist! Posição: **{len(bot.playlist)}**")

@bot.command()
@apenas_no_canal(CANAL_MUSICA)
async def skip(ctx):
    """Pula a música atual"""
    if bot.voice_client and bot.voice_client.is_playing():
        bot.voice_client.stop()
        await ctx.send("⏭️ Música pulada!")
    else:
        await ctx.send("❌ Nenhuma música está tocando.")

@bot.command()
@apenas_no_canal(CANAL_MUSICA)
async def stop(ctx):
    """Para a música e desconecta"""
    if bot.voice_client:
        bot.radio_playing = False
        await bot.voice_client.disconnect()
        bot.voice_client = None
        await ctx.send("⏹️ Música parada e desconectado!")
    else:
        await ctx.send("❌ Não estou conectado a nenhum canal.")

@bot.command()
@apenas_no_canal(CANAL_MUSICA)
async def radio(ctx):
    """Inicia a rádio 24/7"""
    if not ctx.author.voice:
        return await ctx.send("❌ Você precisa estar em um canal de voz!")

    channel = ctx.author.voice.channel

    if not bot.voice_client:
        bot.voice_client = await channel.connect()

    bot.radio_playing = True
    await ctx.send("📻 **Rádio 24/7 iniciada!** Música ambiente contínua.")

# ================== COMANDOS DE RPG ==================
@bot.command()
@apenas_no_canal(CANAL_JOGOS)
async def criar_char(ctx, classe: str, *, nome: str):
    """Cria um personagem RPG"""
    if classe.lower() not in classes_rpg:
        return await ctx.send("❌ Classes disponíveis: guerreiro, mago, ladino")

    if get_rpg_player(ctx.author.id):
        return await ctx.send("❌ Você já tem um personagem!")

    criar_personagem(ctx.author.id, classe.lower(), nome)
    stats = classes_rpg[classe.lower()]

    embed = discord.Embed(title="⚔️ Personagem Criado!", color=discord.Color.gold())
    embed.add_field(name="Nome", value=nome, inline=True)
    embed.add_field(name="Classe", value=classe.title(), inline=True)
    embed.add_field(name="Nível", value="1", inline=True)
    embed.add_field(name="❤️ Vida", value=f"{stats['vida']}", inline=True)
    embed.add_field(name="⚔️ Ataque", value=f"{stats['ataque']}", inline=True)
    embed.add_field(name="🛡️ Defesa", value=f"{stats['defesa']}", inline=True)

    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_JOGOS)
async def status_rpg(ctx, member: discord.Member = None):
    """Mostra status do personagem RPG"""
    target = member or ctx.author
    player = get_rpg_player(target.id)

    if not player:
        return await ctx.send(f"❌ {'Você não tem' if not member else f'{member.display_name} não tem'} um personagem!")

    embed = discord.Embed(title=f"⚔️ {player['nome']}", color=discord.Color.blue())
    embed.add_field(name="Classe", value=player['classe'].title(), inline=True)
    embed.add_field(name="Nível", value=player['nivel'], inline=True)
    embed.add_field(name="XP", value=player['xp'], inline=True)
    embed.add_field(name="❤️ Vida", value=f"{player['vida_atual']}/{player['vida_max']}", inline=True)
    embed.add_field(name="⚔️ Ataque", value=player['ataque'], inline=True)
    embed.add_field(name="🛡️ Defesa", value=player['defesa'], inline=True)
    embed.add_field(name="💰 Gold", value=player['gold'], inline=True)

    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_JOGOS)
async def aventura(ctx):
    """Vai em uma aventura RPG"""
    player = get_rpg_player(ctx.author.id)
    if not player:
        return await ctx.send("❌ Você precisa criar um personagem primeiro!")

    # Eventos aleatórios de aventura
    eventos = [
        {"nome": "Goblin Selvagem", "dificuldade": 15, "recompensa": random.randint(50, 150), "xp": 20},
        {"nome": "Tesouro Escondido", "dificuldade": 10, "recompensa": random.randint(100, 300), "xp": 15},
        {"nome": "Dragão Jovem", "dificuldade": 25, "recompensa": random.randint(200, 500), "xp": 50}
    ]

    evento = random.choice(eventos)
    sucesso = random.randint(1, 20) + player['agilidade'] >= evento['dificuldade']

    if sucesso:
        player['gold'] += evento['recompensa']
        player['xp'] += evento['xp']
        rpg_data[str(ctx.author.id)] = player
        save_json(RPG_FILE, rpg_data)

        embed = discord.Embed(title="✅ Aventura Bem-sucedida!", color=discord.Color.green())
        embed.description = f"Você enfrentou um **{evento['nome']}** e venceu!"
        embed.add_field(name="💰 Gold Ganho", value=evento['recompensa'], inline=True)
        embed.add_field(name="⭐ XP Ganho", value=evento['xp'], inline=True)
    else:
        dano = random.randint(10, 30)
        player['vida_atual'] = max(0, player['vida_atual'] - dano)
        rpg_data[str(ctx.author.id)] = player
        save_json(RPG_FILE, rpg_data)

        embed = discord.Embed(title="❌ Aventura Fracassada!", color=discord.Color.red())
        embed.description = f"Você enfrentou um **{evento['nome']}** e foi derrotado!"
        embed.add_field(name="❤️ Dano Recebido", value=dano, inline=True)

    await ctx.send(embed=embed)

# ================== COMANDOS DE BLACKJACK ==================
# Armazenar jogos ativos
jogos_blackjack = {}

def valor_mao(mao):
    valor = 0
    ases = 0
    for carta in mao:
        if carta in ['J', 'Q', 'K']:
            valor += 10
        elif carta == 'A':
            ases += 1
            valor += 11
        else:
            valor += int(carta)

    while valor > 21 and ases:
        valor -= 10
        ases -= 1

    return valor

@bot.command()
@apenas_no_canal(CANAL_JOGOS)
async def blackjack(ctx, aposta: int):
    """Joga BlackJack"""
    if aposta <= 0:
        return await ctx.send("❌ Aposta deve ser positiva!")

    saldo = get_saldo(ctx.author.id)
    if saldo < aposta:
        return await ctx.send(f"❌ Saldo insuficiente! Você tem {saldo} moedas.")

    if ctx.author.id in jogos_blackjack:
        return await ctx.send("❌ Você já tem um jogo em andamento! Use `&stand` para finalizar.")

    # Criar baralho
    cartas = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K'] * 4
    random.shuffle(cartas)

    # Distribuir cartas
    jogador = [cartas.pop(), cartas.pop()]
    dealer = [cartas.pop(), cartas.pop()]

    # Salvar jogo
    jogos_blackjack[ctx.author.id] = {
        "jogador": jogador,
        "dealer": dealer,
        "baralho": cartas,
        "aposta": aposta,
        "saldo_original": saldo
    }

    valor_jogador = valor_mao(jogador)

    embed = discord.Embed(title="🃏 BlackJack", color=discord.Color.gold())
    embed.add_field(name="Suas cartas", value=f"{' '.join(jogador)} (Valor: {valor_jogador})", inline=False)
    embed.add_field(name="Dealer", value=f"{dealer[0]} ?", inline=False)
    embed.add_field(name="Aposta", value=f"{aposta} moedas", inline=True)

    if valor_jogador == 21:
        # BlackJack!
        ganho = int(aposta * 2.5)
        set_saldo(ctx.author.id, saldo + ganho)
        embed.color = discord.Color.green()
        embed.add_field(name="🎉 BLACKJACK!", value=f"Você ganhou {ganho} moedas!", inline=False)
        del jogos_blackjack[ctx.author.id]
    elif valor_jogador > 21:
        # Bust
        set_saldo(ctx.author.id, saldo - aposta)
        embed.color = discord.Color.red()
        embed.add_field(name="💥 BUST!", value=f"Você perdeu {aposta} moedas!", inline=False)
        del jogos_blackjack[ctx.author.id]
    else:
        embed.add_field(name="Ações", value="Digite `&hit` para mais uma carta ou `&stand` para parar", inline=False)

    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_JOGOS)
async def hit(ctx):
    """Pede mais uma carta no BlackJack"""
    if ctx.author.id not in jogos_blackjack:
        return await ctx.send("❌ Você não tem um jogo ativo! Use `&blackjack <aposta>` para começar.")

    jogo = jogos_blackjack[ctx.author.id]
    nova_carta = jogo["baralho"].pop()
    jogo["jogador"].append(nova_carta)

    valor_jogador = valor_mao(jogo["jogador"])

    embed = discord.Embed(title="🃏 BlackJack - Hit", color=discord.Color.gold())
    embed.add_field(name="Nova carta", value=nova_carta, inline=True)
    embed.add_field(name="Suas cartas", value=f"{' '.join(jogo['jogador'])} (Valor: {valor_jogador})", inline=False)
    embed.add_field(name="Dealer", value=f"{jogo['dealer'][0]} ?", inline=False)

    if valor_jogador > 21:
        # Bust
        set_saldo(ctx.author.id, jogo["saldo_original"] - jogo["aposta"])
        embed.color = discord.Color.red()
        embed.add_field(name="💥 BUST!", value=f"Você perdeu {jogo['aposta']} moedas!", inline=False)
        del jogos_blackjack[ctx.author.id]
    elif valor_jogador == 21:
        embed.add_field(name="✨ 21!", value="Use `&stand` para finalizar", inline=False)
    else:
        embed.add_field(name="Ações", value="Digite `&hit` para mais uma carta ou `&stand` para parar", inline=False)

    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_JOGOS)
async def stand(ctx):
    """Para de pedir cartas e finaliza o jogo"""
    if ctx.author.id not in jogos_blackjack:
        return await ctx.send("❌ Você não tem um jogo ativo! Use `&blackjack <aposta>` para começar.")

    jogo = jogos_blackjack[ctx.author.id]
    
    # Dealer joga
    while valor_mao(jogo["dealer"]) < 17:
        jogo["dealer"].append(jogo["baralho"].pop())

    valor_jogador = valor_mao(jogo["jogador"])
    valor_dealer = valor_mao(jogo["dealer"])

    embed = discord.Embed(title="🃏 BlackJack - Resultado", color=discord.Color.blue())
    embed.add_field(name="Suas cartas", value=f"{' '.join(jogo['jogador'])} (Valor: {valor_jogador})", inline=False)
    embed.add_field(name="Dealer", value=f"{' '.join(jogo['dealer'])} (Valor: {valor_dealer})", inline=False)

    if valor_dealer > 21:
        # Dealer bust
        ganho = jogo["aposta"] * 2
        set_saldo(ctx.author.id, jogo["saldo_original"] + ganho)
        embed.color = discord.Color.green()
        embed.add_field(name="🎉 DEALER BUST!", value=f"Você ganhou {ganho} moedas!", inline=False)
    elif valor_jogador > valor_dealer:
        # Jogador vence
        ganho = jogo["aposta"] * 2
        set_saldo(ctx.author.id, jogo["saldo_original"] + ganho)
        embed.color = discord.Color.green()
        embed.add_field(name="🎉 VOCÊ VENCEU!", value=f"Você ganhou {ganho} moedas!", inline=False)
    elif valor_jogador == valor_dealer:
        # Empate
        embed.color = discord.Color.orange()
        embed.add_field(name="🤝 EMPATE!", value="Sua aposta foi devolvida", inline=False)
    else:
        # Dealer vence
        set_saldo(ctx.author.id, jogo["saldo_original"] - jogo["aposta"])
        embed.color = discord.Color.red()
        embed.add_field(name="😢 DEALER VENCEU!", value=f"Você perdeu {jogo['aposta']} moedas!", inline=False)

    del jogos_blackjack[ctx.author.id]
    await ctx.send(embed=embed)

# ================== COMANDOS DE CRIPTOMOEDAS ==================
@bot.command()
async def crypto(ctx):
    """Mostra preços das criptomoedas"""
    embed = discord.Embed(title="💎 Mercado de Criptomoedas", color=discord.Color.gold())

    for crypto, data in crypto_data.items():
        preco = data["preco"]
        if len(data["historico"]) >= 2:
            variacao = ((preco - data["historico"][-2]) / data["historico"][-2]) * 100
            emoji = "📈" if variacao > 0 else "📉" if variacao < 0 else "➡️"
            embed.add_field(
                name=f"{emoji} {crypto.title()}",
                value=f"💰 {preco:,} moedas\n({variacao:+.1f}%)",
                inline=True
            )
        else:
            embed.add_field(name=f"💎 {crypto.title()}", value=f"💰 {preco:,} moedas", inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def comprar_crypto(ctx, crypto: str, quantidade: int):
    """Compra criptomoedas"""
    crypto = crypto.lower()
    if crypto not in crypto_data:
        return await ctx.send("❌ Criptomoeda não encontrada!")

    preco_unitario = crypto_data[crypto]["preco"]
    custo_total = preco_unitario * quantidade
    saldo = get_saldo(ctx.author.id)

    if saldo < custo_total:
        return await ctx.send(f"❌ Saldo insuficiente! Precisa de {custo_total:,} moedas.")

    # Adicionar ao portfólio do usuário
    user_str = str(ctx.author.id)
    if "portfolio" not in money:
        money["portfolio"] = {}
    if user_str not in money["portfolio"]:
        money["portfolio"][user_str] = {}
    if crypto not in money["portfolio"][user_str]:
        money["portfolio"][user_str][crypto] = 0

    money["portfolio"][user_str][crypto] += quantidade
    set_saldo(ctx.author.id, saldo - custo_total)

    await ctx.send(f"✅ Comprou **{quantidade}** {crypto} por **{custo_total:,}** moedas!")

@bot.command()
async def portfolio(ctx):
    """Mostra seu portfólio de criptomoedas"""
    user_str = str(ctx.author.id)

    if "portfolio" not in money or user_str not in money["portfolio"]:
        return await ctx.send("❌ Você não tem criptomoedas!")

    embed = discord.Embed(title="💼 Seu Portfólio", color=discord.Color.blue())
    valor_total = 0

    for crypto, quantidade in money["portfolio"][user_str].items():
        if quantidade > 0:
            preco_atual = crypto_data[crypto]["preco"]
            valor_crypto = preco_atual * quantidade
            valor_total += valor_crypto

            embed.add_field(
                name=f"💎 {crypto.title()}",
                value=f"Quantidade: {quantidade}\nValor: {valor_crypto:,} moedas",
                inline=True
            )

    embed.add_field(name="💰 Valor Total", value=f"{valor_total:,} moedas", inline=False)
    await ctx.send(embed=embed)

# ================== COMANDOS DE ESTATÍSTICAS ==================
@bot.command()
@apenas_no_canal(CANAL_STATS)
async def grafico_atividade(ctx):
    """Gera gráfico de atividade do servidor"""
    if not atividade_data:
        return await ctx.send("❌ Não há dados de atividade suficientes!")

    # Preparar dados
    dates = []
    mensagens = []
    comandos = []

    for date_str in sorted(atividade_data.keys())[-7:]:  # Últimos 7 dias
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        dates.append(date_obj)

        total_mensagens = sum(user_data.get("mensagens", 0) for user_data in atividade_data[date_str].values())
        total_comandos = sum(user_data.get("comandos", 0) for user_data in atividade_data[date_str].values())

        mensagens.append(total_mensagens)
        comandos.append(total_comandos)

    # Criar gráfico
    plt.figure(figsize=(12, 6))
    plt.subplot(1, 2, 1)
    plt.plot(dates, mensagens, marker='o', color='blue')
    plt.title('Mensagens por Dia')
    plt.xlabel('Data')
    plt.ylabel('Mensagens')
    plt.xticks(rotation=45)

    plt.subplot(1, 2, 2)
    plt.plot(dates, comandos, marker='o', color='red')
    plt.title('Comandos por Dia')
    plt.xlabel('Data')
    plt.ylabel('Comandos')
    plt.xticks(rotation=45)

    plt.tight_layout()

    # Salvar em buffer
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    plt.close()

    file = discord.File(buffer, filename="atividade.png")
    embed = discord.Embed(title="📊 Gráfico de Atividade - Últimos 7 dias", color=discord.Color.green())
    embed.set_image(url="attachment://atividade.png")

    await ctx.send(embed=embed, file=file)

@bot.command()
async def rank_xp(ctx):
    """Mostra ranking de XP"""
    if not xp_data:
        return await ctx.send("❌ Nenhum dado de XP encontrado!")

    # Ordenar por XP
    ranking = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]

    embed = discord.Embed(title="🏆 Ranking de XP - Top 10", color=discord.Color.gold())

    for i, (user_id, data) in enumerate(ranking, 1):
        try:
            user = bot.get_user(int(user_id))
            nome = user.display_name if user else f"Usuário {user_id}"
            embed.add_field(
                name=f"{i}º - {nome}",
                value=f"Nível {data['nivel']} - {data['xp']:,} XP",
                inline=False
            )
        except:
            continue

    await ctx.send(embed=embed)

# ================== COMANDOS ORIGINAIS (MANTIDOS) ==================
@bot.command()
@apenas_no_canal(CANAL_SALDO)
async def saldo(ctx):
    s = get_saldo(ctx.author.id)
    user_xp = get_xp(ctx.author.id)
    embed = discord.Embed(title="💰 Seu Status", color=discord.Color.gold())
    embed.add_field(name="💰 Moedas", value=f"{s:,}", inline=True)
    embed.add_field(name="⭐ XP", value=f"{user_xp['xp']:,}", inline=True)
    embed.add_field(name="🎯 Nível", value=f"{user_xp['nivel']}", inline=True)
    await ctx.send(embed=embed)

USOS_TRABALHAR = {}
LIMITE_USOS = 2
TEMPO_LIMITE = timedelta(hours=4)
LIMITE_GANHO_TOTAL = 50000

@bot.command()
@apenas_no_canal(CANAL_TRABALHO)
async def trabalhar(ctx):
    u = ctx.author.id
    agora = datetime.now()
    dados = USOS_TRABALHAR.get(u, {"usos": 0, "inicio": agora, "ganho": 0})

    if agora - dados["inicio"] > TEMPO_LIMITE:
        dados = {"usos": 0, "inicio": agora, "ganho": 0}

    if dados["usos"] >= LIMITE_USOS:
        return await ctx.send("⏳ Você já trabalhou 2x nas últimas 4h. Espere um pouco!")

    if dados["ganho"] >= LIMITE_GANHO_TOTAL:
        return await ctx.send("💰 Você já atingiu o limite de 50.000 moedas neste período.")

    # Verificar evento sazonal
    evento = evento_ativo()
    bonus_multiplier = evento["bonus_trabalho"] if evento else 1.0

    ganho_base = random.randint(5000, 15000)
    ganho = int(ganho_base * bonus_multiplier)
    ganho = min(ganho, LIMITE_GANHO_TOTAL - dados["ganho"])

    set_saldo(u, get_saldo(u) + ganho)
    dados["usos"] += 1
    dados["ganho"] += ganho
    USOS_TRABALHAR[u] = dados

    # Adicionar XP
    xp_ganho = random.randint(10, 25)
    novo_nivel = add_xp(u, xp_ganho)

    mensagem = f"💼 Você trabalhou e ganhou **{ganho:,} moedas** e **{xp_ganho} XP**!"
    if evento:
        mensagem += f"\n{evento['mensagem']}"
    if novo_nivel:
        mensagem += f"\n🎉 Subiu para o nível **{novo_nivel}**!"

    await ctx.send(mensagem)

@bot.check
async def checar_canal(ctx):
    if ctx.channel.id not in CANAL_AUTORIZADO:
        canais_mention = ", ".join(f"<#{id}>" for id in CANAL_AUTORIZADO[:5])
        await ctx.send(f"❌ Comandos só podem ser usados nos canais autorizados.")
        return False
    return True

# ================== SISTEMA DE LOJA (ORIGINAL MANTIDO) ==================
lojas = [
    {
        "nome": "Temporada Verão",
        "itens": {
            "Sorvete Mágico 🍦": 50000000000,
            "Óculos de Sol Neon 🕶️": 10000000000,
            "Prancha de Surf 🏄": 20000000000,
            "Protetor Solar Encantado 🧴": 150000000000
        }
    },
    {
        "nome": "Festa de Halloween",
        "itens": {
            "Poção Assombrada 🧪": 750000000000,
            "Fantasma de Estimação 👻": 30000000000,
            "Abóbora Encantada 🎃": 120000000000,
            "Capa Sombria 🦇": 180000000000
        }
    },
]

def carregar_indice_loja():
    if os.path.exists(LOJA_STATUS_FILE):
        return load_json(LOJA_STATUS_FILE).get("indice", 0)
    return 0

def salvar_indice_loja(indice):
    save_json(LOJA_STATUS_FILE, {"indice": indice})

loja_atual_index = carregar_indice_loja()
tempo_troca = 3600
ID_DO_CANAL_DE_ANUNCIOS = [1396232612841783316]

async def trocar_loja_periodicamente():
    global loja_atual_index
    await bot.wait_until_ready()
    while not bot.is_closed():
        loja_atual_index = (loja_atual_index + 1) % len(lojas)
        salvar_indice_loja(loja_atual_index)
        atualizar_precos_crypto()  # Atualizar cryptos junto com a loja

        for canal_id in ID_DO_CANAL_DE_ANUNCIOS:
            canal = bot.get_channel(canal_id)
            if canal:
                await canal.send(f"🛍️ A loja mudou para **{lojas[loja_atual_index]['nome']}**! Cryptos atualizadas!")

        await asyncio.sleep(tempo_troca)

# ================== COMANDOS DE HELP ==================
@bot.command()
async def help(ctx):
    embeds = []

    # Help Básico
    embed1 = discord.Embed(title="📚 Comandos Básicos", color=discord.Color.blue())
    embed1.add_field(name="💰 Economia", value="`&saldo` `&trabalhar` `&transferir` `&investir`", inline=False)
    embed1.add_field(name="🛒 Loja", value="`&loja` `&comprar`", inline=False)
    embed1.add_field(name="🎰 Loteria", value="`&comprar_loteria` `&loteria_info`", inline=False)
    embed1.add_field(name="🎲 Jogos", value="`&blackjack` `&dado`", inline=False)
    embeds.append(embed1)

    # Help Música
    embed2 = discord.Embed(title="🎵 Comandos de Música", color=discord.Color.green())
    embed2.add_field(name="Player", value="`&play <url>` `&skip` `&stop`", inline=False)
    embed2.add_field(name="Playlist", value="`&queue <url>`", inline=False)
    embed2.add_field(name="Rádio", value="`&radio` (24/7)", inline=False)
    embeds.append(embed2)

    # Help RPG
    embed3 = discord.Embed(title="⚔️ Comandos RPG", color=discord.Color.red())
    embed3.add_field(name="Personagem", value="`&criar_char <classe> <nome>`", inline=False)
    embed3.add_field(name="Status", value="`&status_rpg` `&aventura`", inline=False)
    embed3.add_field(name="Classes", value="guerreiro, mago, ladino", inline=False)
    embeds.append(embed3)

    # Help Crypto & Stats
    embed4 = discord.Embed(title="💎 Crypto & Estatísticas", color=discord.Color.purple())
    embed4.add_field(name="Crypto", value="`&crypto` `&comprar_crypto` `&portfolio`", inline=False)
    embed4.add_field(name="Stats", value="`&grafico_atividade` `&rank_xp`", inline=False)
    embeds.append(embed4)

    # Enviar todos os embeds
    for embed in embeds:
        await ctx.send(embed=embed)

# ================== COMANDOS DE INTERAÇÃO (MANTIDOS) ==================
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latência: {round(bot.latency * 1000)}ms")

@bot.command()
async def abraco(ctx, m: discord.Member):
    gifs = [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExYmV5cGdsYjJrbjI3ZWp4MjF2c2VvcGZidnI2bzBuYW83ajQ2MWF0dCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/svXXBgduBsJ1u/giphy.gif",
    ]
    gif_url = random.choice(gifs)
    embed = discord.Embed(description=f"{ctx.author.mention} abraçou {m.mention} 🤗", color=discord.Color.purple())
    embed.set_image(url=gif_url)
    await ctx.send(embed=embed)

@bot.command()
async def dado(ctx, tipo_dado: str = "1d6"):
    try:
        partes = tipo_dado.lower().split('d')
        if len(partes) != 2:
            raise ValueError("Formato inválido")

        quantidade = int(partes[0]) if partes[0] else 1
        faces = int(partes[1])

        if quantidade < 1 or quantidade > 10:
            return await ctx.send("❌ Quantidade deve ser entre 1 e 10 dados")
        if faces not in [4, 6, 8, 10, 12, 20]:
            return await ctx.send("❌ Dado inválido. Use d4, d6, d8, d10, d12 ou d20")

        resultados = [random.randint(1, faces) for _ in range(quantidade)]
        total = sum(resultados)

        embed = discord.Embed(title="🎲 Rolagem de Dados", color=discord.Color.blue())
        embed.add_field(name=f"Rolando {quantidade}d{faces}", value=f"```{', '.join(map(str, resultados))}```", inline=False)

        if quantidade > 1:
            embed.add_field(name="Total", value=f"**{total}**", inline=True)

        await ctx.send(embed=embed)
    except ValueError:
        await ctx.send("❌ Formato inválido. Use `&dado XdY` (ex: `&dado 2d6`)")

# ================== COMANDOS DE ECONOMIA (FALTANTES) ==================
@bot.command()
@apenas_no_canal(CANAL_TRANSACOES)
async def transferir(ctx, membro: discord.Member, valor: int):
    """Transfere moedas para outro usuário"""
    if valor <= 0:
        return await ctx.send("❌ Valor deve ser positivo!")
    
    saldo_atual = get_saldo(ctx.author.id)
    if saldo_atual < valor:
        return await ctx.send(f"❌ Saldo insuficiente! Você tem {saldo_atual:,} moedas.")
    
    if membro.bot:
        return await ctx.send("❌ Não é possível transferir para bots!")
    
    set_saldo(ctx.author.id, saldo_atual - valor)
    set_saldo(membro.id, get_saldo(membro.id) + valor)
    
    embed = discord.Embed(title="💸 Transferência Realizada", color=discord.Color.green())
    embed.add_field(name="De", value=ctx.author.mention, inline=True)
    embed.add_field(name="Para", value=membro.mention, inline=True)
    embed.add_field(name="Valor", value=f"{valor:,} moedas", inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_INVESTIR)
async def investir(ctx, valor: int):
    """Investe moedas com chance de lucro ou perda"""
    if valor <= 0:
        return await ctx.send("❌ Valor deve ser positivo!")
    
    saldo_atual = get_saldo(ctx.author.id)
    if saldo_atual < valor:
        return await ctx.send(f"❌ Saldo insuficiente! Você tem {saldo_atual:,} moedas.")
    
    # 60% chance de ganhar, 40% de perder
    sucesso = random.random() < 0.6
    
    if sucesso:
        multiplicador = random.uniform(1.2, 2.0)  # 20% a 100% de lucro
        ganho = int(valor * multiplicador) - valor
        set_saldo(ctx.author.id, saldo_atual + ganho)
        
        embed = discord.Embed(title="📈 Investimento Bem-sucedido!", color=discord.Color.green())
        embed.add_field(name="Investido", value=f"{valor:,} moedas", inline=True)
        embed.add_field(name="Lucro", value=f"{ganho:,} moedas", inline=True)
        embed.add_field(name="Total", value=f"{valor + ganho:,} moedas", inline=True)
    else:
        perda = random.randint(int(valor * 0.3), valor)  # Perde 30% a 100%
        set_saldo(ctx.author.id, saldo_atual - perda)
        
        embed = discord.Embed(title="📉 Investimento Fracassou!", color=discord.Color.red())
        embed.add_field(name="Investido", value=f"{valor:,} moedas", inline=True)
        embed.add_field(name="Perda", value=f"{perda:,} moedas", inline=True)
        embed.add_field(name="Restou", value=f"{saldo_atual - perda:,} moedas", inline=True)
    
    await ctx.send(embed=embed)

# ================== COMANDOS DE LOJA E LOTERIA ==================
@bot.command()
@apenas_no_canal(CANAL_LOJA)
async def loja(ctx):
    """Mostra a loja atual"""
    loja_atual = lojas[loja_atual_index]
    
    embed = discord.Embed(title=f"🛍️ {loja_atual['nome']}", color=discord.Color.blue())
    
    for item, preco in loja_atual['itens'].items():
        embed.add_field(name=item, value=f"{preco:,} moedas", inline=True)
    
    embed.set_footer(text="Use &comprar <item> para comprar um item!")
    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_LOJA)
async def comprar(ctx, *, item_nome: str):
    """Compra um item da loja"""
    loja_atual = lojas[loja_atual_index]
    
    # Procurar item (case insensitive)
    item_encontrado = None
    preco_item = 0
    
    for item, preco in loja_atual['itens'].items():
        if item_nome.lower() in item.lower():
            item_encontrado = item
            preco_item = preco
            break
    
    if not item_encontrado:
        return await ctx.send("❌ Item não encontrado na loja atual!")
    
    saldo_atual = get_saldo(ctx.author.id)
    if saldo_atual < preco_item:
        return await ctx.send(f"❌ Saldo insuficiente! Você precisa de {preco_item:,} moedas.")
    
    set_saldo(ctx.author.id, saldo_atual - preco_item)
    
    embed = discord.Embed(title="✅ Compra Realizada!", color=discord.Color.green())
    embed.add_field(name="Item", value=item_encontrado, inline=True)
    embed.add_field(name="Preço", value=f"{preco_item:,} moedas", inline=True)
    embed.add_field(name="Saldo Restante", value=f"{saldo_atual - preco_item:,} moedas", inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_LOTERIA)
async def comprar_loteria(ctx, *numeros):
    """Compra um bilhete da loteria (6 números de 1 a 60)"""
    if len(numeros) != 6:
        return await ctx.send("❌ Você deve escolher exatamente 6 números!")
    
    try:
        nums = [int(n) for n in numeros]
        if any(n < 1 or n > 60 for n in nums):
            return await ctx.send("❌ Números devem estar entre 1 e 60!")
        if len(set(nums)) != 6:
            return await ctx.send("❌ Não pode repetir números!")
    except ValueError:
        return await ctx.send("❌ Use apenas números!")
    
    preco_bilhete = 10000
    saldo_atual = get_saldo(ctx.author.id)
    
    if saldo_atual < preco_bilhete:
        return await ctx.send(f"❌ Você precisa de {preco_bilhete:,} moedas para comprar um bilhete!")
    
    set_saldo(ctx.author.id, saldo_atual - preco_bilhete)
    
    # Adicionar ao acumulado
    loteria["acumulado"] += preco_bilhete
    
    # Salvar números do jogador
    user_str = str(ctx.author.id)
    if user_str not in loteria["numeros"]:
        loteria["numeros"][user_str] = []
    
    loteria["numeros"][user_str].append(sorted(nums))
    save_loteria(loteria)
    
    embed = discord.Embed(title="🎫 Bilhete Comprado!", color=discord.Color.gold())
    embed.add_field(name="Seus números", value=f"{sorted(nums)}", inline=False)
    embed.add_field(name="Prêmio acumulado", value=f"{loteria['acumulado']:,} moedas", inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@apenas_no_canal(CANAL_LOTERIA)
async def loteria_info(ctx):
    """Mostra informações da loteria"""
    embed = discord.Embed(title="🎰 Informações da Loteria", color=discord.Color.purple())
    embed.add_field(name="💰 Prêmio Acumulado", value=f"{loteria['acumulado']:,} moedas", inline=False)
    embed.add_field(name="🎫 Preço do Bilhete", value="10.000 moedas", inline=True)
    embed.add_field(name="🎯 Como Jogar", value="Escolha 6 números de 1 a 60", inline=True)
    
    user_str = str(ctx.author.id)
    if user_str in loteria["numeros"] and loteria["numeros"][user_str]:
        bilhetes = len(loteria["numeros"][user_str])
        embed.add_field(name="📋 Seus Bilhetes", value=f"{bilhetes} bilhete(s)", inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def sortear_loteria(ctx):
    """Sorteia a loteria (apenas admins)"""
    if not loteria["numeros"]:
        return await ctx.send("❌ Nenhum bilhete foi comprado!")
    
    # Sortear números vencedores
    numeros_sorteados = sorted(random.sample(range(1, 61), 6))
    
    # Verificar vencedores
    vencedores = []
    for user_id, bilhetes in loteria["numeros"].items():
        for bilhete in bilhetes:
            acertos = len(set(bilhete) & set(numeros_sorteados))
            if acertos >= 4:  # 4+ acertos ganham
                vencedores.append((user_id, acertos))
    
    embed = discord.Embed(title="🎰 Resultado da Loteria!", color=discord.Color.gold())
    embed.add_field(name="🎯 Números Sorteados", value=f"{numeros_sorteados}", inline=False)
    
    if vencedores:
        # Dividir prêmio entre vencedores
        premio_individual = loteria["acumulado"] // len(vencedores)
        
        vencedores_texto = []
        for user_id, acertos in vencedores:
            user = bot.get_user(int(user_id))
            nome = user.display_name if user else f"Usuário {user_id}"
            set_saldo(int(user_id), get_saldo(int(user_id)) + premio_individual)
            vencedores_texto.append(f"{nome} ({acertos} acertos)")
        
        embed.add_field(name="🏆 Vencedores", value="\n".join(vencedores_texto), inline=False)
        embed.add_field(name="💰 Prêmio Individual", value=f"{premio_individual:,} moedas", inline=True)
        
        # Salvar no histórico
        loteria["historico"].append({
            "data": datetime.now().isoformat(),
            "numeros": numeros_sorteados,
            "vencedores": len(vencedores),
            "premio": loteria["acumulado"]
        })
        
        # Resetar loteria
        loteria["acumulado"] = 0
        loteria["numeros"] = {}
    else:
        embed.add_field(name="😢 Nenhum Vencedor", value="Prêmio acumula para o próximo sorteio!", inline=False)
    
    save_loteria(loteria)
    await ctx.send(embed=embed)

# ================== COMANDOS SOCIAIS ==================
@bot.command()
async def beijar(ctx, membro: discord.Member):
    """Beija outro usuário"""
    if membro == ctx.author:
        return await ctx.send("❌ Você não pode beijar a si mesmo!")
    
    gifs = [
        "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
        "https://media.giphy.com/media/bm2O3nXTcKJeU/giphy.gif"
    ]
    
    embed = discord.Embed(
        description=f"{ctx.author.mention} beijou {membro.mention} 💋", 
        color=discord.Color.pink()
    )
    embed.set_image(url=random.choice(gifs))
    await ctx.send(embed=embed)

@bot.command()
async def elogiar(ctx, membro: discord.Member):
    """Elogia outro usuário"""
    elogios = [
        "é uma pessoa incrível!",
        "tem um coração maravilhoso!",
        "é muito inteligente!",
        "tem uma energia positiva contagiante!",
        "é super talentoso(a)!",
        "ilumina o ambiente por onde passa!"
    ]
    
    embed = discord.Embed(
        description=f"{membro.mention} {random.choice(elogios)} ✨", 
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Elogio enviado por {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command()
async def mimar(ctx, membro: discord.Member):
    """Mima outro usuário"""
    gifs = [
        "https://media.giphy.com/media/ZBQhoZC0nqknSviPqT/giphy.gif",
        "https://media.giphy.com/media/lrr9rHuoJOE0w/giphy.gif"
    ]
    
    embed = discord.Embed(
        description=f"{ctx.author.mention} está mimando {membro.mention} 🥰", 
        color=discord.Color.purple()
    )
    embed.set_image(url=random.choice(gifs))
    await ctx.send(embed=embed)

@bot.command()
async def dancar(ctx, membro: discord.Member = None):
    """Dança com outro usuário ou sozinho"""
    gifs = [
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/3o7abGQa0aRJUurpII/giphy.gif"
    ]
    
    if membro:
        texto = f"{ctx.author.mention} está dançando com {membro.mention} 💃🕺"
    else:
        texto = f"{ctx.author.mention} está dançando sozinho(a)! 💃"
    
    embed = discord.Embed(description=texto, color=discord.Color.orange())
    embed.set_image(url=random.choice(gifs))
    await ctx.send(embed=embed)

# ================== COMANDOS DE MODERAÇÃO ==================
@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, membro: discord.Member, *, motivo: str = "Sem motivo especificado"):
    """Aplica um warn a um usuário"""
    if membro.id == ctx.author.id:
        return await ctx.send("❌ Você não pode dar warn em si mesmo!")
    
    if membro.bot:
        return await ctx.send("❌ Não é possível dar warn em bots!")
    
    user_id_str = str(membro.id)
    if user_id_str not in warns_data:
        warns_data[user_id_str] = []
    
    warn_info = {
        "moderador": str(ctx.author),
        "motivo": motivo,
        "data": datetime.now().isoformat()
    }
    
    warns_data[user_id_str].append(warn_info)
    save_json(WARN_FILE, warns_data)
    
    total_warns = len(warns_data[user_id_str])
    
    embed = discord.Embed(title="⚠️ Warn Aplicado", color=discord.Color.orange())
    embed.add_field(name="Usuário", value=membro.mention, inline=True)
    embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
    embed.add_field(name="Total de Warns", value=total_warns, inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def warns(ctx, membro: discord.Member = None):
    """Mostra os warns de um usuário"""
    target = membro or ctx.author
    user_warns = warns_data.get(str(target.id), [])
    
    if not user_warns:
        return await ctx.send(f"✅ {target.display_name} não possui warns!")
    
    embed = discord.Embed(title=f"⚠️ Warns de {target.display_name}", color=discord.Color.orange())
    
    for i, warn in enumerate(user_warns[-5:], 1):  # Últimos 5 warns
        data = datetime.fromisoformat(warn["data"]).strftime("%d/%m/%Y")
        embed.add_field(
            name=f"Warn #{i}",
            value=f"**Motivo:** {warn['motivo']}\n**Moderador:** {warn['moderador']}\n**Data:** {data}",
            inline=False
        )
    
    embed.set_footer(text=f"Total: {len(user_warns)} warns")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def removewarn(ctx, membro: discord.Member, indice: int):
    """Remove um warn específico"""
    user_id_str = str(membro.id)
    user_warns = warns_data.get(user_id_str, [])
    
    if not user_warns:
        return await ctx.send(f"❌ {membro.display_name} não possui warns!")
    
    if indice < 1 or indice > len(user_warns):
        return await ctx.send(f"❌ Índice inválido! Use um número entre 1 e {len(user_warns)}")
    
    warn_removido = user_warns.pop(indice - 1)
    
    if not user_warns:
        warns_data.pop(user_id_str, None)
    else:
        warns_data[user_id_str] = user_warns
    
    save_json(WARN_FILE, warns_data)
    
    embed = discord.Embed(title="✅ Warn Removido", color=discord.Color.green())
    embed.add_field(name="Usuário", value=membro.mention, inline=True)
    embed.add_field(name="Warn Removido", value=warn_removido["motivo"], inline=True)
    embed.add_field(name="Warns Restantes", value=len(user_warns), inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearwarns(ctx, membro: discord.Member):
    """Remove todos os warns de um usuário"""
    user_id_str = str(membro.id)
    warns_removidos = len(warns_data.get(user_id_str, []))
    
    if warns_removidos == 0:
        return await ctx.send(f"❌ {membro.display_name} não possui warns!")
    
    warns_data.pop(user_id_str, None)
    save_json(WARN_FILE, warns_data)
    
    embed = discord.Embed(title="🧹 Warns Limpos", color=discord.Color.green())
    embed.add_field(name="Usuário", value=membro.mention, inline=True)
    embed.add_field(name="Warns Removidos", value=warns_removidos, inline=True)
    
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def blacklist_add(ctx, membro: discord.Member, *, motivo: str = "Sem motivo"):
    """Adiciona usuário à blacklist"""
    user_id_str = str(membro.id)
    blacklist[user_id_str] = {
        "motivo": motivo,
        "moderador": str(ctx.author),
        "data": datetime.now().isoformat()
    }
    save_json(BLACKLIST_FILE, blacklist)
    
    await ctx.send(f"🚫 {membro.mention} foi adicionado à blacklist!")

@bot.command()
@commands.has_permissions(administrator=True)
async def blacklist_remove(ctx, membro: discord.Member):
    """Remove usuário da blacklist"""
    user_id_str = str(membro.id)
    if user_id_str not in blacklist:
        return await ctx.send(f"❌ {membro.display_name} não está na blacklist!")
    
    blacklist.pop(user_id_str, None)
    save_json(BLACKLIST_FILE, blacklist)
    
    await ctx.send(f"✅ {membro.mention} foi removido da blacklist!")

@bot.command()
async def blacklist_list(ctx):
    """Lista usuários na blacklist"""
    if not blacklist:
        return await ctx.send("✅ Nenhum usuário na blacklist!")
    
    embed = discord.Embed(title="🚫 Lista de Blacklist", color=discord.Color.red())
    
    for user_id, info in list(blacklist.items())[:10]:  # Máximo 10
        user = bot.get_user(int(user_id))
        nome = user.display_name if user else f"Usuário {user_id}"
        data = datetime.fromisoformat(info["data"]).strftime("%d/%m/%Y")
        
        embed.add_field(
            name=nome,
            value=f"**Motivo:** {info['motivo']}\n**Data:** {data}",
            inline=False
        )
    
    await ctx.send(embed=embed)

# ================== COMANDOS ADMIN (MANTIDOS) ==================
@bot.command()
@commands.has_permissions(administrator=True)
async def setsaldo(ctx, membro: discord.Member, valor: int):
    set_saldo(membro.id, valor)
    await ctx.send(f"💰 Saldo de {membro.mention} ajustado para {valor:,} moedas!")

# ================== RUN BOT ==================
TOKEN = "MTM5NTk2ODUwMzE1MTg1NzcxNA.GGluds.G0eTqVbTVAD9IJw1nDMGHhJlwy6w328LN9cG6s"
bot.run(TOKEN)
