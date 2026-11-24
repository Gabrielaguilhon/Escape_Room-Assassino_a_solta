"""
Escape Room estilo FNAF - Front-end (Pygame CE)

Máquina de estados não-bloqueante:
    TELA_INICIAL -> menu inicial (Iniciar Jogo / Instruções). A partida ainda não começou;
                  "Iniciar Jogo" envia 'S' ao Arduino (que arranca o cronômetro) e vai para JOGANDO
    INSTRUCOES -> controles, minigames e regras (ESC/ENTER volta ao menu inicial)
    JOGANDO -> movimento livre pelo mapa; aproximar-se de uma estação e premir E abre o MENU
    MENU       -> confirmação para iniciar o minigame físico (ENTER = sim, ESC = não)
    AGUARDANDO -> envia o ID do minigame por Serial e lê a porta (sem bloquear) até
                  receber "WIN_<ID>" do Arduino. Mostra a última linha "MSG:..." recebida.
                  ESC envia 'X' para o Arduino cancelar o minigame e voltar ao MENU.
    DICA       -> mostra a mensagem de recompensa do minigame (ENTER/ESC para voltar)
    DERROTA    -> o Arduino enviou "GAME_OVER" (tempo esgotado, 3 erros ou assassino errado)
    VITORIA    -> recebeu "WIN_T" (assassino identificado no telefone) ou os 4 minigames
                  foram concluídos: ecrã final de vitória, a partida termina

Protocolo Serial (9600 baud, uma mensagem por linha):
    PC -> Arduino: S (iniciar partida), R | G | M | T (iniciar minigame), X (cancelar minigame)
    Arduino -> PC: WIN_R | WIN_G | WIN_M | WIN_T, GAME_OVER, MSG:<texto para o ecrã>

Controlos: WASD para mover, E para interagir.
Gráficos: pixel art em assets/ (estações + sprite sheet do jogador), escalado sem suavização.
Decoração: cartazes de procurados na parede e armas do crime no chão (assets/decoracao.jfif).
Derrota: o mago toca a animação de morte (linha 16 da sprite sheet) e fica caído.
Cheat de teste: F9 no estado AGUARDANDO simula a vitória.
"""

import math
import os
import random
import sys
import pygame

try:
    import serial
except ImportError:  # permite correr o jogo mesmo sem pyserial instalado
    serial = None

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
LARGURA, ALTURA = 800, 600
FPS = 60

# Serial (ajustar à porta do Arduino: ver Gestor de Dispositivos > Portas COM)
PORTA_SERIAL = "COM5"
BAUDRATE = 9600

# Estados
TELA_INICIAL = "TELA_INICIAL"  # menu inicial (a partida ainda não começou)
INSTRUCOES = "INSTRUCOES"      # aba de instruções (a partida ainda não começou)
JOGANDO = "JOGANDO"
MENU = "MENU"
AGUARDANDO = "AGUARDANDO"
DICA = "DICA"
DERROTA = "DERROTA"
VITORIA = "VITORIA"

PASTA_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Sala: espessura das paredes (a de cima é mais alta para mostrar a "face" da parede,
# onde ficam pendurados os cartazes de procurados e o Genius)
PAREDE_TOPO = 140
PAREDE_LADO = 24
PAREDE_BAIXO = 24
AREA_SALA = pygame.Rect(
    PAREDE_LADO, PAREDE_TOPO,
    LARGURA - 2 * PAREDE_LADO, ALTURA - PAREDE_TOPO - PAREDE_BAIXO,
)
TAMANHO_AZULEJO = 32

# Cores
PRETO = (10, 10, 14)
AZULEJO_CLARO = (44, 42, 54)
AZULEJO_ESCURO = (18, 17, 23)
PAREDE_FACE = (38, 36, 50)
PAREDE_FACE_LINHA = (30, 28, 40)
PAREDE_TOPO_COR = (22, 21, 30)
PAREDE_BORDA = (62, 58, 78)
RODAPE = (14, 13, 18)
BRANCO = (230, 230, 230)
VERMELHO = (200, 30, 30)
AMARELO = (240, 200, 60)
CINZENTO = (120, 120, 130)
VERDE = (60, 200, 90)

# Borda preta uniforme à volta dos objetos dos minigames
BORDA_OBJETOS = (0, 0, 0)
ESPESSURA_BORDA = 3

# ---------------------------------------------------------------------------
# Minigames e respetivas dicas
# ---------------------------------------------------------------------------
MINIGAMES = {
    "Radio": {
        "id": "R",
        "descricao": "Sintonize a frequência certa com o potenciómetro. Siga o buzzer.",
        "hardware": "Potenciómetro + Buzzer",
        "dica": "Dica: Um batom foi encontrado na cena do crime.",
        "pos": (140, 175),
        "cor": (90, 160, 220),
        "imagem": "radio.png",
        "largura": 84,
    },
    "Genius": {
        "id": "G",
        "descricao": "Repita a sequência de luzes nos 4 LEDs sem errar.",
        "hardware": "4 LEDs + 4 botões",
        "dica": "Dica: Foi encontrado um OCULOS e um OBJETO PONTIAGUDO na cena do crime.",
        "pos": (640, 100),  # pendurado na parede de cima (em baixo, para se alcançar)
        "cor": (220, 160, 60),
        "imagem": "genius.png",
        # o PNG tem duas fileiras de luzes: usa-se só a de cima
        "recorte": (0, 0, 553, 215),
        "largura": 170,
    },
    "Telegrafo": {
        "id": "M",
        "descricao": "Transmita a mensagem correta em código Morse.",
        "hardware": "Botão de telégrafo (Morse)",
        "dica": "Dica: Foi encontrado um FIO DE CABELO RUIVO na cena do crime!",
        "pos": (140, 470),
        "cor": (170, 100, 220),
        "imagem": "telegrafo.png",
        "largura": 96,
    },
    "Telefone": {
        "id": "T",
        "descricao": "Marque o nome do assassino no teclado T9 do telefone.",
        "hardware": "Teclado matricial (T9)",
        "dica": "A linha cai... Se o nome estiver certo, a porta destranca!",
        "pos": (655, 470),
        "cor": (80, 200, 140),
        "imagem": "telefone.png",
        "largura": 112,
    },
}

# Distância (em píxeis, à volta da hitbox da estação) a que o jogador pode interagir
MARGEM_INTERACAO = 28

# Jogador: sprite sheet 4 colunas x 18 linhas; ordem das direções nas linhas
SHEET_COLUNAS, SHEET_LINHAS = 4, 18
DIRECOES = ("baixo", "cima", "esquerda", "direita")
LINHA_IDLE = 0   # linhas 0-3
LINHA_WALK = 4   # linhas 4-7
LINHA_MORTE = 16  # penúltima linha: o mago a cair (4 frames)
ESCALA_PLAYER = 5

# ---------------------------------------------------------------------------
# Decoração (assets/decoracao.jfif): retângulos de recorte na imagem original
# ---------------------------------------------------------------------------
IMAGEM_DECORACAO = "decoracao.jfif"
# Cartazes de procurados (metade de cima, sem o título "CARTAZES DE PROCURADOS")
CARTAZES = {
    "ANAB": (46, 132, 641, 706),
    "CHUCK": (712, 132, 638, 706),
    "SAMARA": (1400, 132, 638, 706),
    "NOIVA": (2065, 132, 640, 706),
}
LARGURA_CARTAZ = 34                    # cartazes pequenos, presos no mural
LARGURA_CARTAZ_GRANDE = 176            # cartazes ampliados no ecrã da discagem (Telefone)
ROTACAO_CARTAZES = (-4, 3, -2, 5)      # ligeiramente tortos, como num mural real
MURAL = pygame.Rect(64, 30, 220, 84)   # quadro de cortiça na parede (mural de investigação)
X_PORTA = 482        # centro da porta trancada (entre o mural e o Genius)

# Armas do crime (metade de baixo: só o quadrado cinza, sem o rótulo de texto)
# nome: (recorte, largura no ecrã, centro no chão, rotação em graus)
# Pequenas e encostadas aos cantos/paredes, cada uma com um marcador de evidência
ARMAS = {
    "VENENO": ((66, 920, 614, 425), 15, (742, 206), 0),
    "FACA": ((1407, 920, 614, 425), 24, (632, 338), 30),
    "SERRA": ((2072, 920, 614, 425), 36, (232, 322), -6),
    "ESPINGARDA": ((731, 920, 614, 425), 52, (318, 526), -6),
}
TOLERANCIA_FUNDO_ARMAS = 30  # quanto uma cor pode diferir do cinza de fundo

# Contorno de giz de um corpo no chão (cena do crime), perto da faca
CENTRO_GIZ = (585, 300)


# ---------------------------------------------------------------------------
# Comunicação Serial (não-bloqueante)
# ---------------------------------------------------------------------------
class ConexaoSerial:
    """
    Envolve o pyserial com leitura não-bloqueante.
    Se a porta não abrir, o jogo continua a funcionar em modo offline
    (útil para testar com o cheat F9 enquanto o hardware não está pronto).
    """

    def __init__(self, porta, baudrate):
        self.porta = porta
        self.ser = None
        self.buffer = b""
        self.erro = None
        if serial is None:
            self.erro = "pyserial não instalado"
            return
        try:
            # timeout=0 -> read() devolve logo o que houver, nunca espera
            self.ser = serial.Serial(porta, baudrate, timeout=0, write_timeout=0)
        except (serial.SerialException, ValueError) as e:
            self.erro = str(e)
            self.ser = None

    @property
    def ligada(self):
        return self.ser is not None and self.ser.is_open

    def enviar(self, texto):
        if not self.ligada:
            return False
        try:
            self.ser.write((texto + "\n").encode("ascii"))
            return True
        except (serial.SerialException, serial.SerialTimeoutException) as e:
            self._falha(e)
            return False

    def ler_linhas(self):
        """Devolve as linhas completas recebidas desde a última chamada (lista, pode ser vazia)."""
        if not self.ligada:
            return []
        try:
            n = self.ser.in_waiting
            if n:
                self.buffer += self.ser.read(n)
        except serial.SerialException as e:
            self._falha(e)
            return []

        # Decodifica só linhas completas (evita partir caracteres UTF-8 a meio)
        *linhas, self.buffer = self.buffer.split(b"\n")
        texto = (l.decode("utf-8", errors="ignore").strip() for l in linhas)
        return [l for l in texto if l]

    def _falha(self, e):
        self.erro = str(e)
        try:
            self.ser.close()
        except Exception:
            pass
        self.ser = None

    def fechar(self):
        if self.ligada:
            self.ser.close()


# ---------------------------------------------------------------------------
# Gráficos (pixel art)
# ---------------------------------------------------------------------------
def carregar_imagem(nome):
    """Carrega um PNG da pasta assets com transparência (requer display já criado)."""
    return pygame.image.load(os.path.join(PASTA_ASSETS, nome)).convert_alpha()


def escalar_nitido(superficie, largura=None, altura=None, fator=None):
    """
    Escala com vizinho-mais-próximo (pygame.transform.scale não suaviza),
    mantendo a proporção e o pixel art nítido.
    """
    w, h = superficie.get_size()
    if fator is not None:
        novo = (round(w * fator), round(h * fator))
    elif largura is not None:
        novo = (largura, round(h * largura / w))
    else:
        novo = (round(w * altura / h), altura)
    return pygame.transform.scale(superficie, novo)


def recortar_transparencia(superficie):
    """Remove as margens totalmente transparentes à volta da imagem."""
    return superficie.subsurface(superficie.get_bounding_rect()).copy()


def criar_contorno(imagem, cor, espessura=2):
    """Gera um contorno pixelado (a partir da máscara alfa) para destacar um objeto."""
    silhueta = pygame.mask.from_surface(imagem).to_surface(
        setcolor=cor, unsetcolor=(0, 0, 0, 0)
    )
    w, h = imagem.get_size()
    contorno = pygame.Surface((w + 2 * espessura, h + 2 * espessura), pygame.SRCALPHA)
    for ox in range(-espessura, espessura + 1):
        for oy in range(-espessura, espessura + 1):
            if ox or oy:
                contorno.blit(silhueta, (espessura + ox, espessura + oy))
    return contorno


def limpar_fundo(imagem, limiar_alfa=64, limiar_branco=225):
    """
    Uniformiza o recorte de um PNG:
    - pixels quase brancos ligados ao exterior (restos de fundo branco) ficam transparentes;
    - o alfa é binarizado (0 ou 255), eliminando halos semi-transparentes à volta do objeto.
    O branco *interior* (ex.: mostrador do rádio) não é tocado, por não tocar no exterior.
    """
    img = imagem.copy()
    w, h = img.get_size()

    def fundo(x, y):
        r, g, b, a = img.get_at((x, y))
        return a < limiar_alfa or (r >= limiar_branco and g >= limiar_branco and b >= limiar_branco)

    # Flood fill a partir das bordas da imagem, só através de pixels "de fundo"
    visitado = bytearray(w * h)
    pilha = [(x, y) for x in range(w) for y in (0, h - 1)]
    pilha += [(x, y) for y in range(h) for x in (0, w - 1)]
    img.lock()
    while pilha:
        x, y = pilha.pop()
        i = y * w + x
        if visitado[i] or not fundo(x, y):
            continue
        visitado[i] = 1
        img.set_at((x, y), (0, 0, 0, 0))
        if x > 0: pilha.append((x - 1, y))
        if x < w - 1: pilha.append((x + 1, y))
        if y > 0: pilha.append((x, y - 1))
        if y < h - 1: pilha.append((x, y + 1))

    # Binarizar o alfa dos pixels restantes
    for y in range(h):
        for x in range(w):
            r, g, b, a = img.get_at((x, y))
            if 0 < a < 255:
                img.set_at((x, y), (r, g, b, 255) if a >= limiar_alfa else (0, 0, 0, 0))
    img.unlock()
    return img


def adicionar_borda(imagem, cor=(0, 0, 0), espessura=3):
    """Devolve a imagem com uma borda uniforme (seguindo a silhueta) à volta."""
    borda = criar_contorno(imagem, cor, espessura)
    borda.blit(imagem, (espessura, espessura))
    return borda


def carregar_frames_player():
    """
    Recorta a sprite sheet (4 colunas x 18 linhas) e devolve
    {"idle"/"walk": {direção: [frames]}}.
    Todos os frames usam o MESMO retângulo de recorte (a união das áreas visíveis),
    para que a personagem não "salte" entre frames.
    """
    sheet = carregar_imagem("player.png")
    fw = sheet.get_width() // SHEET_COLUNAS
    fh = sheet.get_height() // SHEET_LINHAS

    linhas_usadas = range(LINHA_IDLE, LINHA_WALK + len(DIRECOES))
    brutos = {
        (lin, col): sheet.subsurface((col * fw, lin * fh, fw, fh))
        for lin in linhas_usadas
        for col in range(SHEET_COLUNAS)
    }

    uniao = None
    for frame in brutos.values():
        r = frame.get_bounding_rect()
        if r.width and r.height:
            uniao = r if uniao is None else uniao.union(r)
    if uniao is None:
        uniao = pygame.Rect(0, 0, fw, fh)

    def recortar(lin, col):
        return escalar_nitido(brutos[(lin, col)].subsurface(uniao).copy(), fator=ESCALA_PLAYER)

    return {
        anim: {
            direcao: [recortar(base + i, col) for col in range(SHEET_COLUNAS)]
            for i, direcao in enumerate(DIRECOES)
        }
        for anim, base in (("idle", LINHA_IDLE), ("walk", LINHA_WALK))
    }


def carregar_frames_morte():
    """
    Recorta os 4 frames da animação de morte (linha LINHA_MORTE).
    Como o mago acaba deitado, o recorte é maior que o dos outros frames; por isso
    devolve também o "ponto dos pés" (em píxeis do frame escalado), usado para o
    desenhar exatamente no sítio onde estava o jogador.
    """
    sheet = carregar_imagem("player.png")
    fw = sheet.get_width() // SHEET_COLUNAS
    fh = sheet.get_height() // SHEET_LINHAS

    # Retângulo de referência = o mesmo dos frames normais (para alinhar os pés)
    ref = None
    for lin in range(LINHA_IDLE, LINHA_WALK + len(DIRECOES)):
        for col in range(SHEET_COLUNAS):
            r = sheet.subsurface((col * fw, lin * fh, fw, fh)).get_bounding_rect()
            if r.width and r.height:
                ref = r if ref is None else ref.union(r)
    ref = ref or pygame.Rect(0, 0, fw, fh)

    brutos = [sheet.subsurface((col * fw, LINHA_MORTE * fh, fw, fh))
              for col in range(SHEET_COLUNAS)]
    uniao = ref.copy()
    for frame in brutos:
        r = frame.get_bounding_rect()
        if r.width and r.height:
            uniao.union_ip(r)

    frames = [escalar_nitido(f.subsurface(uniao).copy(), fator=ESCALA_PLAYER) for f in brutos]
    pes = ((ref.centerx - uniao.x) * ESCALA_PLAYER, (ref.bottom - uniao.y) * ESCALA_PLAYER)
    return frames, pes


def remover_fundo_solido(imagem, tolerancia):
    """
    Torna transparente o fundo de cor sólida (amostrado no canto) ligado às bordas
    da imagem. O que está dentro do contorno do objeto não é afetado.
    """
    img = imagem.convert_alpha()
    cor_fundo = img.get_at((2, 2))
    parecido = pygame.mask.from_threshold(
        img, cor_fundo, (tolerancia, tolerancia, tolerancia, 255))
    w, h = img.get_size()
    fundo = pygame.mask.Mask((w, h))
    bordas = [(x, y) for x in range(0, w, 4) for y in (0, h - 1)]
    bordas += [(x, y) for y in range(0, h, 4) for x in (0, w - 1)]
    for pos in bordas:
        if parecido.get_at(pos) and not fundo.get_at(pos):
            fundo.draw(parecido.connected_component(pos), (0, 0))
    # Alarga 1 píxel para apanhar a franja de compressão JPEG à volta do objeto
    for desvio in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        fundo.draw(fundo.copy(), desvio)
    buraco = fundo.to_surface(setcolor=(0, 0, 0, 255), unsetcolor=(0, 0, 0, 0))
    img.blit(buraco, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    return img


def carregar_decoracao():
    """Devolve ([cartazes], [(arma, centro), ...]) já recortados e escalados."""
    folha = pygame.image.load(os.path.join(PASTA_ASSETS, IMAGEM_DECORACAO)).convert()

    cartazes = []
    for rect, angulo in zip(CARTAZES.values(), ROTACAO_CARTAZES):
        img = pygame.transform.smoothscale_by(folha.subsurface(rect), LARGURA_CARTAZ / rect[2])
        # papel envelhecido: tom sépia suave
        img.fill((235, 220, 190), special_flags=pygame.BLEND_RGB_MULT)
        img = img.convert_alpha()
        cartazes.append(pygame.transform.rotate(img, angulo))

    armas = []
    for rect, largura, centro, angulo in ARMAS.values():
        img = remover_fundo_solido(folha.subsurface(rect), TOLERANCIA_FUNDO_ARMAS)
        img = recortar_transparencia(img)
        img = pygame.transform.smoothscale_by(img, largura / img.get_width())
        # um pouco mais escuras, para não competirem com os objetos dos minigames
        img.fill((200, 195, 190), special_flags=pygame.BLEND_RGB_MULT)
        if angulo:
            img = pygame.transform.rotate(img, angulo)
        armas.append((img, centro))
    return cartazes, armas


def carregar_cartazes_grandes():
    """Cartazes dos suspeitos em tamanho legível (consulta durante a discagem)."""
    folha = pygame.image.load(os.path.join(PASTA_ASSETS, IMAGEM_DECORACAO)).convert()
    return [pygame.transform.smoothscale_by(folha.subsurface(rect), LARGURA_CARTAZ_GRANDE / rect[2])
            for rect in CARTAZES.values()]


def criar_luz(largura, altura, cor, expoente=2.0):
    """Mancha de luz radial suave (para somar ao cenário com BLEND_RGB_ADD)."""
    n = 48
    luz = pygame.Surface((n, n))
    meio = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            d = min(1.0, math.hypot(x - meio, y - meio) / meio)
            k = (1 - d) ** expoente
            luz.set_at((x, y), [int(c * k) for c in cor])
    return pygame.transform.smoothscale(luz, (largura, altura))


def criar_vinheta(largura, altura, alfa_max=190, inicio=0.6):
    """Escurecimento suave nas bordas do ecrã (desenhado por cima de tudo no mapa)."""
    pw, ph = 80, 60
    v = pygame.Surface((pw, ph), pygame.SRCALPHA)
    for y in range(ph):
        for x in range(pw):
            d = math.hypot((x - (pw - 1) / 2) / (pw / 2), (y - (ph - 1) / 2) / (ph / 2))
            t = max(0.0, min(1.0, (d - inicio) / (1.35 - inicio)))
            v.set_at((x, y), (0, 0, 0, int(alfa_max * t ** 1.5)))
    return pygame.transform.smoothscale(v, (largura, altura))


def sombra_suave(largura, altura, alfa=110, camadas=5):
    """Elipse de sombra com bordas suaves (várias elipses sobrepostas)."""
    s = pygame.Surface((largura, altura), pygame.SRCALPHA)
    for i in range(camadas):
        r = s.get_rect().inflate(-i * largura // (camadas * 2), -i * altura // (camadas * 2))
        pygame.draw.ellipse(s, (0, 0, 0, alfa // camadas), r)
    return s


def desenhar_marcador(fundo, fonte, pos, numero):
    """Marcador amarelo de evidência (estilo perícia) com um número."""
    x, y = pos
    pygame.draw.polygon(fundo, (0, 0, 0), [(x - 6, y + 9), (x + 8, y + 9), (x + 5, y - 3), (x - 3, y - 3)])
    pygame.draw.polygon(fundo, (214, 170, 40), [(x - 7, y + 8), (x + 7, y + 8), (x + 4, y - 4), (x - 4, y - 4)])
    pygame.draw.line(fundo, (240, 205, 80), (x - 4, y - 4), (x + 4, y - 4))
    t = fonte.render(str(numero), True, (20, 16, 10))
    fundo.blit(t, t.get_rect(center=(x, y + 2)))


def desenhar_contorno_giz(fundo, centro):
    """Contorno de giz de um corpo caído (sutil, semitransparente)."""
    pontos = [(23, 26), (34, 22), (42, 8), (47, 10), (40, 24), (62, 24), (82, 14), (96, 10),
              (98, 15), (84, 22), (70, 30), (84, 38), (98, 46), (95, 51), (80, 44), (62, 36),
              (40, 36), (46, 50), (41, 53), (33, 38), (23, 34)]
    giz = pygame.Surface((104, 62), pygame.SRCALPHA)
    pygame.draw.lines(giz, (225, 225, 215, 85), True, pontos, 2)
    pygame.draw.circle(giz, (225, 225, 215, 85), (14, 30), 9, 2)
    fundo.blit(giz, giz.get_rect(center=centro))


def criar_cenario():
    """Pré-desenha a sala (piso, paredes, mural, armas e iluminação) numa única superfície."""
    rng = random.Random(13)  # aleatoriedade fixa: a sala é sempre igual
    fundo = pygame.Surface((LARGURA, ALTURA))
    fundo.fill(PAREDE_TOPO_COR)
    fonte_mini = pygame.font.Font(None, 15)

    # --- piso de tábuas de madeira escura ---
    sala = AREA_SALA
    alt_tabua = 18
    for y in range(sala.top, sala.bottom, alt_tabua):
        x = sala.left - rng.randint(0, 90)
        while x < sala.right:
            comp = rng.randint(70, 150)
            tabua = pygame.Rect(x, y, comp, alt_tabua).clip(sala)
            x += comp
            if tabua.width < 3 or tabua.height < 6:
                continue
            v = rng.randint(-7, 7)
            base = (50 + v, 35 + v * 3 // 4, 26 + v // 2)
            fundo.fill(base, tabua)
            veio = (base[0] - 8, base[1] - 7, base[2] - 6)
            for _ in range(rng.randint(1, 3)):  # veios da madeira
                gy = rng.randint(tabua.top + 3, tabua.bottom - 4)
                gx = rng.randint(tabua.left, max(tabua.left, tabua.right - 20))
                pygame.draw.line(fundo, veio, (gx, gy),
                                 (min(gx + rng.randint(12, 60), tabua.right - 2), gy))
            pygame.draw.line(fundo, (base[0] + 9, base[1] + 7, base[2] + 5),
                             tabua.topleft, (tabua.right - 1, tabua.top))
            pygame.draw.line(fundo, (20, 14, 10), (tabua.right - 1, tabua.top),
                             (tabua.right - 1, tabua.bottom - 1))
            pygame.draw.line(fundo, (24, 17, 12), (tabua.left, tabua.bottom - 1),
                             (tabua.right - 1, tabua.bottom - 1))
            if rng.random() < 0.25:  # pregos nas pontas
                fundo.fill((22, 18, 15), (tabua.left + 3, tabua.centery - 1, 2, 2))

    # Poeira / manchas no chão
    manchas = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for _ in range(18):
        cx, cy = rng.randint(sala.left, sala.right), rng.randint(sala.top, sala.bottom)
        w, h = rng.randint(30, 90), rng.randint(12, 34)
        pygame.draw.ellipse(manchas, (0, 0, 0, rng.randint(12, 26)), (cx, cy, w, h))
    fundo.blit(manchas, (0, 0))

    # --- cena do crime no chão: contorno de giz ---
    desenhar_contorno_giz(fundo, CENTRO_GIZ)

    # --- parede de cima (face visível) ---
    face = pygame.Rect(PAREDE_LADO, 16, LARGURA - 2 * PAREDE_LADO, PAREDE_TOPO - 16)
    y_rail, y_rodape = face.top + 82, face.bottom - 8

    # Papel de parede escuro às riscas verticais
    fundo.fill((36, 44, 41), (face.left, face.top, face.width, y_rail - face.top))
    for i, x in enumerate(range(face.left, face.right, 10)):
        if i % 2:
            fundo.fill((31, 38, 35), (x, face.top, 10, y_rail - face.top))
        if i % 4 == 0:  # pequenos motivos do papel de parede
            for y in range(face.top + 10 + (i % 8) * 2, y_rail - 4, 16):
                fundo.fill((44, 53, 49), (x + 4, y, 2, 2))
    # Manchas de humidade/desgaste
    for _ in range(6):
        cx, cy = rng.randint(face.left, face.right), rng.randint(face.top, y_rail - 10)
        mancha = sombra_suave(rng.randint(40, 90), rng.randint(20, 40), alfa=45)
        fundo.blit(mancha, mancha.get_rect(center=(cx, cy)))

    # Cornija no topo e calha (rail) de madeira
    fundo.fill((26, 22, 20), (face.left, face.top, face.width, 6))
    fundo.fill((58, 40, 28), (face.left, y_rail, face.width, 5))
    pygame.draw.line(fundo, (84, 60, 42), (face.left, y_rail), (face.right, y_rail))
    # Lambril de madeira com almofadas
    fundo.fill((44, 30, 22), (face.left, y_rail + 5, face.width, y_rodape - y_rail - 5))
    for x in range(face.left + 6, face.right - 40, 56):
        painel = pygame.Rect(x, y_rail + 10, 48, y_rodape - y_rail - 15)
        pygame.draw.rect(fundo, (34, 23, 17), painel, 2)
        pygame.draw.line(fundo, (60, 42, 30), painel.bottomleft, painel.bottomright)
    fundo.fill(RODAPE, (face.left, y_rodape, face.width, 8))

    # Sombra em gradiente do teto para baixo
    gradiente = pygame.Surface((face.width, 40), pygame.SRCALPHA)
    for i in range(40):
        pygame.draw.line(gradiente, (0, 0, 0, 140 - i * 3), (0, i), (face.width, i))
    fundo.blit(gradiente, face.topleft)

    # --- porta trancada (a saída da sala) ---
    porta = pygame.Rect(0, 0, 52, 94)
    porta.midbottom = (X_PORTA, y_rodape + 8)
    aro = porta.inflate(10, 6).move(0, -3)
    fundo.fill((20, 14, 12), aro)
    pygame.draw.rect(fundo, (70, 50, 36), aro, 2)
    fundo.fill((54, 32, 26), porta)
    for r in (pygame.Rect(porta.left + 7, porta.top + 8, porta.width - 14, 32),
              pygame.Rect(porta.left + 7, porta.top + 48, porta.width - 14, 38)):
        pygame.draw.rect(fundo, (36, 20, 16), r, 2)
        pygame.draw.line(fundo, (70, 44, 34), r.bottomleft, r.bottomright)
    pygame.draw.circle(fundo, (190, 150, 60), (porta.right - 8, porta.centery + 4), 3)
    # Teclado de segurança com a luz vermelha de trancada
    teclado = pygame.Rect(porta.right + 8, porta.top + 30, 10, 16)
    fundo.fill((14, 14, 18), teclado)
    pygame.draw.rect(fundo, (80, 80, 90), teclado, 1)
    fundo.fill(VERMELHO, (teclado.x + 3, teclado.y + 3, 4, 3))
    # Placa "SAÍDA" por cima da porta
    placa = fonte_mini.render("SAÍDA", True, (255, 70, 60))
    caixa_placa = placa.get_rect(midbottom=(porta.centerx, aro.top - 3)).inflate(8, 4)
    fundo.fill((18, 10, 10), caixa_placa)
    pygame.draw.rect(fundo, (90, 30, 30), caixa_placa, 1)
    fundo.blit(placa, placa.get_rect(center=caixa_placa.center))

    # --- mural de investigação (quadro de cortiça com os cartazes) ---
    mural = MURAL
    fundo.fill((0, 0, 0), mural.move(3, 4))  # sombra na parede
    cortica = mural.inflate(-8, -8)
    fundo.fill((118, 84, 52), cortica)
    for _ in range(260):  # textura da cortiça
        px = rng.randint(cortica.left, cortica.right - 2)
        py = rng.randint(cortica.top, cortica.bottom - 2)
        fundo.fill(rng.choice([(98, 68, 40), (134, 98, 62), (106, 74, 46)]), (px, py, 2, 1))
    pygame.draw.rect(fundo, (62, 42, 28), mural, 4)
    pygame.draw.rect(fundo, (92, 66, 44), mural, 1)

    # Notas e fotos soltas no mural
    notas = ((cortica.left + 5, cortica.bottom - 18, 26, 15, (205, 195, 150)),
             (cortica.right - 31, cortica.bottom - 17, 22, 14, (190, 200, 205)),
             (cortica.centerx - 12, cortica.bottom - 15, 24, 12, (215, 205, 165)))
    for nx, ny, w, h, cor in notas:
        fundo.fill((0, 0, 0), (nx + 1, ny + 1, w, h))
        fundo.fill(cor, (nx, ny, w, h))
        for ly in range(ny + 3, ny + h - 2, 3):
            pygame.draw.line(fundo, (90, 90, 100), (nx + 3, ly), (nx + w - rng.randint(4, 10), ly))

    cartazes, armas = carregar_decoracao()
    pinos = []
    passo = (cortica.width - 8) / len(cartazes)
    for i, cartaz in enumerate(cartazes):
        cx = round(cortica.left + 4 + passo * (i + 0.5))
        r = cartaz.get_rect(midtop=(cx, cortica.top + 1 + (i % 2) * 3))
        sombra = cartaz.copy()
        sombra.fill((0, 0, 0, 120), special_flags=pygame.BLEND_RGBA_MULT)
        fundo.blit(sombra, r.move(2, 2))
        fundo.blit(cartaz, r)
        pinos.append((r.centerx, r.top + 4))

    # Fio vermelho a ligar os suspeitos à nota central (como num mural de investigação)
    nota_central = (cortica.centerx, cortica.bottom - 14)
    fios = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for a, b in list(zip(pinos, pinos[1:])) + [(pinos[0], nota_central), (pinos[-1], nota_central)]:
        pygame.draw.line(fios, (215, 30, 30, 230), a, b, 2)
    fundo.blit(fios, (0, 0))
    for p in pinos + [nota_central]:
        pygame.draw.circle(fundo, (0, 0, 0), (p[0] + 1, p[1] + 1), 2)
        pygame.draw.circle(fundo, (220, 30, 30), p, 2)

    # Relógio de parede parado (à direita do Genius)
    relogio = (752, 50)
    pygame.draw.circle(fundo, (0, 0, 0), (relogio[0] + 2, relogio[1] + 2), 12)
    pygame.draw.circle(fundo, (70, 52, 34), relogio, 12)
    pygame.draw.circle(fundo, (190, 182, 160), relogio, 9)
    pygame.draw.line(fundo, (20, 20, 20), relogio, (relogio[0], relogio[1] - 7), 2)
    pygame.draw.line(fundo, (20, 20, 20), relogio, (relogio[0] + 5, relogio[1] + 2), 1)

    # Arandelas (luzes de parede) a ladear a porta
    arandelas = [(X_PORTA - 54, 56), (X_PORTA + 54, 56)]
    for ax, ay in arandelas:
        fundo.fill((30, 24, 18), (ax - 2, ay, 5, 10))
        pygame.draw.polygon(fundo, (210, 170, 100),
                            [(ax - 6, ay), (ax + 6, ay), (ax + 3, ay - 8), (ax - 3, ay - 8)])

    # --- armas no chão (decorativas, sem colisão), com marcadores de evidência ---
    for i, (img, centro) in enumerate(armas, start=1):
        r = img.get_rect(center=centro)
        s = sombra_suave(img.get_width() + 8, 10, alfa=120)
        fundo.blit(s, s.get_rect(center=(r.centerx + 2, r.bottom - 2)))
        fundo.blit(img, r)
        desenhar_marcador(fundo, fonte_mini, (r.right + 9, r.bottom - 6), i)

    # --- iluminação ---
    # Candeeiro de teto: poça de luz quente ao centro da sala
    luz = criar_luz(640, 420, (56, 40, 20))
    fundo.blit(luz, luz.get_rect(center=(LARGURA // 2, sala.centery - 10)),
               special_flags=pygame.BLEND_RGB_ADD)
    # Luz das arandelas na parede
    for ax, ay in arandelas:
        brilho = criar_luz(120, 96, (80, 56, 26))
        fundo.blit(brilho, brilho.get_rect(center=(ax, ay - 4)), special_flags=pygame.BLEND_RGB_ADD)

    # Sombra que a parede de cima projeta no chão (suave)
    faixa = pygame.Surface((sala.width, 22), pygame.SRCALPHA)
    for i in range(22):
        pygame.draw.line(faixa, (0, 0, 0, int(170 * (1 - i / 22) ** 2)), (0, i), (sala.width, i))
    fundo.blit(faixa, sala.topleft)
    # Sombras junto às paredes laterais e de baixo
    for i in range(14):
        a = int(140 * (1 - i / 14) ** 2)
        linha = pygame.Surface((1, sala.height), pygame.SRCALPHA)
        linha.fill((0, 0, 0, a))
        fundo.blit(linha, (sala.left + i, sala.top))
        fundo.blit(linha, (sala.right - 1 - i, sala.top))
        base = pygame.Surface((sala.width, 1), pygame.SRCALPHA)
        base.fill((0, 0, 0, a))
        fundo.blit(base, (sala.left, sala.bottom - 1 - i))

    # --- contorno das paredes ---
    pygame.draw.rect(fundo, (12, 11, 16), (0, 0, LARGURA, ALTURA), 4)
    pygame.draw.rect(fundo, PAREDE_BORDA,
                     (PAREDE_LADO - 2, 14, LARGURA - 2 * PAREDE_LADO + 4,
                      ALTURA - 14 - PAREDE_BAIXO + 2), 2)
    return fundo


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------
class Player:
    """Jogador animado (idle/walk em 4 direções) que se move com WASD."""

    VEL_ANIM = {"idle": 5, "walk": 10}  # frames por segundo

    VEL_MORTE = 5  # frames por segundo da animação de morte

    def __init__(self, x, y, frames, frames_morte=None, velocidade=200):
        self.frames = frames
        self.frames_morte, self.pes_morte = frames_morte or ([], (0, 0))
        self.morto = False
        self.direcao = "baixo"
        self.anim = "idle"
        self.tempo_anim = 0.0
        self.velocidade = velocidade  # píxeis por segundo

        # Hitbox só nos pés: permite passar "atrás" dos objetos de forma natural
        largura_sprite, altura_sprite = frames["idle"]["baixo"][0].get_size()
        self.rect = pygame.Rect(0, 0, int(largura_sprite * 0.7), int(altura_sprite * 0.25))
        self.rect.center = (x, y)
        # posição em float para movimento suave independente do FPS
        self.x, self.y = float(self.rect.x), float(self.rect.y)

    def atualizar(self, dt, teclas, obstaculos=()):
        dx = (teclas[pygame.K_d] - teclas[pygame.K_a])
        dy = (teclas[pygame.K_s] - teclas[pygame.K_w])

        # Direção e animação
        if dx or dy:
            if dx:
                self.direcao = "direita" if dx > 0 else "esquerda"
            else:
                self.direcao = "baixo" if dy > 0 else "cima"
            novo_anim = "walk"
        else:
            novo_anim = "idle"
        if novo_anim != self.anim:
            self.anim = novo_anim
            self.tempo_anim = 0.0
        self.tempo_anim += dt

        if dx and dy:  # normalizar diagonal
            dx *= 0.7071
            dy *= 0.7071

        # Mover um eixo de cada vez para deslizar ao longo dos obstáculos
        self.x += dx * self.velocidade * dt
        self.rect.x = round(self.x)
        for obs in obstaculos:
            if self.rect.colliderect(obs):
                if dx > 0:
                    self.rect.right = obs.left
                elif dx < 0:
                    self.rect.left = obs.right
                self.x = float(self.rect.x)

        self.y += dy * self.velocidade * dt
        self.rect.y = round(self.y)
        for obs in obstaculos:
            if self.rect.colliderect(obs):
                if dy > 0:
                    self.rect.bottom = obs.top
                elif dy < 0:
                    self.rect.top = obs.bottom
                self.y = float(self.rect.y)

        # Paredes: o jogador não sai da área da sala
        antes = self.rect.topleft
        self.rect.clamp_ip(AREA_SALA)
        if self.rect.topleft != antes:
            self.x, self.y = float(self.rect.x), float(self.rect.y)

    def morrer(self):
        """Inicia a animação de morte (toca uma vez e fica no último frame)."""
        if self.frames_morte and not self.morto:
            self.morto = True
            self.tempo_anim = 0.0

    def desenhar_morte(self, ecra, pes):
        """Desenha o frame atual da morte com os pés do mago no ponto `pes`."""
        i = min(int(self.tempo_anim * self.VEL_MORTE), len(self.frames_morte) - 1)
        ecra.blit(self.frames_morte[i], (pes[0] - self.pes_morte[0], pes[1] - self.pes_morte[1]))

    @property
    def imagem(self):
        lista = self.frames[self.anim][self.direcao]
        return lista[int(self.tempo_anim * self.VEL_ANIM[self.anim]) % len(lista)]

    @property
    def base(self):
        """Coordenada y usada para ordenar o desenho (profundidade)."""
        return self.rect.bottom

    def desenhar(self, ecra):
        img = self.imagem
        # Sombra elíptica nos pés
        sombra = pygame.Surface((self.rect.width, 10), pygame.SRCALPHA)
        pygame.draw.ellipse(sombra, (0, 0, 0, 110), sombra.get_rect())
        ecra.blit(sombra, sombra.get_rect(center=(self.rect.centerx, self.rect.bottom - 2)))
        if self.morto:
            self.desenhar_morte(ecra, (self.rect.centerx, self.rect.bottom + 2))
            return
        ecra.blit(img,img.get_rect(midbottom=(self.rect.centerx, self.rect.bottom + 2)))


class Estacao:
    """Ponto do mapa onde se inicia um minigame físico."""

    def __init__(self, nome, dados):
        self.nome = nome
        self.dados = dados
        self.concluido = False

        img = carregar_imagem(dados["imagem"])
        if "recorte" in dados:
            img = img.subsurface(dados["recorte"])
        img = recortar_transparencia(limpar_fundo(recortar_transparencia(img)))
        # Escala primeiro e só depois põe a borda, para que tenha a mesma espessura
        # no ecrã em todos os objetos (independente da resolução de cada PNG)
        img = escalar_nitido(img, largura=dados["largura"] - 2 * ESPESSURA_BORDA)
        self.imagem = adicionar_borda(img, BORDA_OBJETOS, ESPESSURA_BORDA)

        # Versão "desligada" (escurecida) para quando o minigame já foi resolvido
        self.imagem_concluida = self.imagem.copy()
        self.imagem_concluida.fill((95, 95, 105), special_flags=pygame.BLEND_RGB_MULT)
        self.contorno = criar_contorno(self.imagem, AMARELO)

        # Hitbox = retângulo da imagem; obstáculo físico = metade de baixo do objeto
        # (o jogador pode passar "por trás" da parte de cima, dando profundidade)
        self.rect = self.imagem.get_rect(center=dados["pos"])
        self.solido = pygame.Rect(
            self.rect.left + 4, self.rect.centery,
            self.rect.width - 8, self.rect.height // 2 - 2,
        )
        # Sombra suave no chão (o Genius está pendurado na parede: não tem)
        self.sombra = None
        if self.rect.centery > PAREDE_TOPO:
            self.sombra = sombra_suave(int(self.rect.width * 1.05), 22, alfa=150)

    @property
    def base(self):
        return self.rect.bottom

    def perto_de(self, player):
        zona = self.rect.inflate(2 * MARGEM_INTERACAO, 2 * MARGEM_INTERACAO)
        return zona.colliderect(player.rect)

    def desenhar(self, ecra, fonte, destacado):
        if self.sombra:
            ecra.blit(self.sombra, self.sombra.get_rect(center=(self.rect.centerx + 3,
                                                                self.rect.bottom - 4)))
        if destacado:
            ecra.blit(self.contorno, self.contorno.get_rect(center=self.rect.center))
        ecra.blit(self.imagem_concluida if self.concluido else self.imagem, self.rect)

        txt = fonte.render(self.nome, False, CINZENTO if self.concluido else BRANCO)
        caixa = txt.get_rect(midtop=(self.rect.centerx, self.rect.bottom + 4)).inflate(8, 4)
        pygame.draw.rect(ecra, PRETO, caixa)
        ecra.blit(txt, txt.get_rect(center=caixa.center))
        if self.concluido:
            ok = fonte.render("OK", False, VERDE)
            fundo_ok = ok.get_rect(center=self.rect.center).inflate(8, 4)
            pygame.draw.rect(ecra, PRETO, fundo_ok)
            pygame.draw.rect(ecra, VERDE, fundo_ok, 1)
            ecra.blit(ok, ok.get_rect(center=fundo_ok.center))


# ---------------------------------------------------------------------------
# Jogo
# ---------------------------------------------------------------------------
class Jogo:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Escape Room")
        self.ecra = pygame.display.set_mode((LARGURA, ALTURA))
        self.relogio = pygame.time.Clock()
        self.fonte = pygame.font.Font(None, 22)
        self.fonte_media = pygame.font.Font(None, 28)
        self.fonte_grande = pygame.font.Font(None, 40)
        self.fonte_titulo = pygame.font.Font(None, 96)
        self.fonte_pequena = pygame.font.Font(None, 19)

        # Gráficos (convert_alpha exige o display já criado)
        self.cenario = criar_cenario()
        self.vinheta = criar_vinheta(LARGURA, ALTURA)
        self.fundo_menu, self.fundo_instrucoes = self.criar_fundos_menu()
        self.cartazes_grandes = carregar_cartazes_grandes()
        self.player = Player(LARGURA // 2, ALTURA // 2 + 40,
                             carregar_frames_player(), carregar_frames_morte())
        self.estacoes = [Estacao(nome, dados) for nome, dados in MINIGAMES.items()]
        self.obstaculos = [est.solido for est in self.estacoes]

        self.serial = ConexaoSerial(PORTA_SERIAL, BAUDRATE)
        if self.serial.ligada:
            print(f"[Serial] Ligado a {PORTA_SERIAL} @ {BAUDRATE}")
        else:
            print(f"[Serial] Modo offline ({self.serial.erro}). Use F9 para simular vitórias.")

        # O jogo começa no menu inicial: a partida (e o cronômetro) só arranca em "Iniciar Jogo"
        self.estado = TELA_INICIAL
        self.opcao_menu = 0          # índice da opção selecionada no menu inicial
        self.relogio_anim = 0.0      # tempo para animações do menu (luz a piscar)
        self.minigame_atual = None  # nome do minigame selecionado
        self.tempo_aguardando = 0.0
        self.ultima_msg = ""  # última linha "MSG:..." recebida do Arduino
        self.a_correr = True

    # --- transições de estado -------------------------------------------
    def mudar_estado(self, novo, minigame=None):
        self.estado = novo
        if novo == DERROTA:
            self.player.morrer()
        if minigame is not None:
            self.minigame_atual = minigame

    def estacao_proxima(self):
        for est in self.estacoes:
            if est.perto_de(self.player):
                return est
        return None

    def iniciar_minigame_fisico(self, nome):
        """Envia o ID do minigame ao Arduino e passa a AGUARDANDO (sem esperar aqui)."""
        ident = MINIGAMES[nome]["id"]
        if self.serial.enviar(ident):
            print(f"[Serial] Enviado: {ident}")
        self.tempo_aguardando = 0.0
        self.ultima_msg = ""
        self.mudar_estado(AGUARDANDO, nome)

    def vitoria(self, nome):
        """
        Minigame concluído: marca a estação e mostra a dica.
        Se for o telefone (assassino identificado) ou se já não faltar nenhum
        minigame, o jogo termina imediatamente com o ecrã de VITÓRIA.
        """
        for est in self.estacoes:
            if est.nome == nome:
                est.concluido = True
        if MINIGAMES[nome]["id"] == "T" or all(est.concluido for est in self.estacoes):
            print("[Jogo] VITÓRIA!")
            self.mudar_estado(VITORIA, nome)
        else:
            self.mudar_estado(DICA, nome)

    def cancelar_minigame(self):
        """Pede ao Arduino para abandonar o minigame (desliga LEDs/buzzer e volta ao MENU)."""
        if self.serial.enviar("X"):
            print("[Serial] Enviado: X")

    def verificar_serial(self):
        """
        Chamado a cada frame (em qualquer estado): lê só o que já chegou e regressa logo.
        - GAME_OVER  -> tela de derrota, seja qual for o estado atual
        - MSG:<txt>  -> guardado para mostrar no ecrã de AGUARDANDO
        - WIN_<ID>   -> só conta se for o minigame que está em curso
        """
        for linha in self.serial.ler_linhas():
            print(f"[Serial] Recebido: {linha}")
            if self.estado in (TELA_INICIAL, INSTRUCOES, DERROTA, VITORIA):
                continue  # partida ainda não começou ou já encerrou: ignora
            if linha == "GAME_OVER":
                self.mudar_estado(DERROTA)
                return
            if linha.startswith("MSG:"):
                self.ultima_msg = linha[4:].strip()
            elif (self.estado == AGUARDANDO
                  and linha == "WIN_" + MINIGAMES[self.minigame_atual]["id"]):
                self.vitoria(self.minigame_atual)

    # --- menu inicial e instruções ----------------------------------------
    OPCOES_MENU = ("Iniciar Jogo", "Instruções")

    def botoes_menu(self):
        """Retângulos clicáveis das opções do menu inicial (mesma ordem de OPCOES_MENU)."""
        botoes = []
        for i in range(len(self.OPCOES_MENU)):
            r = pygame.Rect(0, 0, 300, 52)
            r.center = (LARGURA // 2, 372 + i * 72)
            botoes.append(r)
        return botoes

    def botao_voltar(self):
        r = pygame.Rect(0, 0, 230, 36)
        r.midbottom = (LARGURA // 2, ALTURA - 14)
        return r

    def escolher_opcao_menu(self, indice):
        if indice == 0:
            self.iniciar_partida()
        else:
            self.mudar_estado(INSTRUCOES)

    def iniciar_partida(self):
        """Sai do menu: avisa o Arduino (que arranca o cronômetro) e entra no mapa."""
        if self.serial.enviar("S"):
            print("[Serial] Enviado: S (início da partida)")
        print("[Jogo] Partida iniciada.")
        self.mudar_estado(JOGANDO)

    def tratar_evento_tela_inicial(self, evento):
        n = len(self.OPCOES_MENU)
        if evento.type == pygame.KEYDOWN:
            if evento.key in (pygame.K_w, pygame.K_UP):
                self.opcao_menu = (self.opcao_menu - 1) % n
            elif evento.key in (pygame.K_s, pygame.K_DOWN):
                self.opcao_menu = (self.opcao_menu + 1) % n
            elif evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.escolher_opcao_menu(self.opcao_menu)
            elif evento.key == pygame.K_ESCAPE:
                self.a_correr = False
        elif evento.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.botoes_menu()):
                if r.collidepoint(evento.pos):
                    self.opcao_menu = i
        elif evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
            for i, r in enumerate(self.botoes_menu()):
                if r.collidepoint(evento.pos):
                    self.opcao_menu = i
                    self.escolher_opcao_menu(i)

    def tratar_evento_instrucoes(self, evento):
        if evento.type == pygame.KEYDOWN and evento.key in (
                pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_BACKSPACE):
            self.mudar_estado(TELA_INICIAL)
        elif (evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1
              and self.botao_voltar().collidepoint(evento.pos)):
            self.mudar_estado(TELA_INICIAL)

    # --- eventos ----------------------------------------------------------
    def tratar_eventos(self):
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                self.a_correr = False
            elif self.estado == TELA_INICIAL:
                self.tratar_evento_tela_inicial(evento)
            elif self.estado == INSTRUCOES:
                self.tratar_evento_instrucoes(evento)
            elif evento.type == pygame.KEYDOWN:
                if self.estado == JOGANDO:
                    if evento.key == pygame.K_e:
                        est = self.estacao_proxima()
                        if est:
                            self.mudar_estado(MENU, est.nome)
                    elif evento.key == pygame.K_ESCAPE:
                        self.a_correr = False

                elif self.estado == MENU:
                    if evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.iniciar_minigame_fisico(self.minigame_atual)
                    elif evento.key == pygame.K_ESCAPE:
                        self.mudar_estado(JOGANDO)

                elif self.estado == AGUARDANDO:
                    if evento.key == pygame.K_F9:  # CHEAT: simula "WIN_<ID>"
                        print(f"[Cheat] WIN_{MINIGAMES[self.minigame_atual]['id']} simulado")
                        # Se houver hardware ligado, tira o Arduino do minigame
                        self.cancelar_minigame()
                        self.vitoria(self.minigame_atual)
                    elif evento.key == pygame.K_ESCAPE:  # desistir e voltar ao mapa
                        self.cancelar_minigame()
                        self.mudar_estado(JOGANDO)

                elif self.estado == DICA:
                    if evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                        self.mudar_estado(JOGANDO)

                elif self.estado in (DERROTA, VITORIA):
                    if evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                        self.a_correr = False

    # --- lógica -----------------------------------------------------------
    def atualizar(self, dt):
        self.relogio_anim += dt
        # A Serial é lida em todos os estados para apanhar o GAME_OVER a qualquer momento
        self.verificar_serial()
        if self.estado == JOGANDO:
            self.player.atualizar(dt, pygame.key.get_pressed(), self.obstaculos)
        elif self.estado == AGUARDANDO:
            self.tempo_aguardando += dt
        elif self.estado == DERROTA:
            self.player.tempo_anim += dt  # anima a morte do mago

    # --- desenho ----------------------------------------------------------
    def desenhar_mapa(self):
        self.ecra.blit(self.cenario, (0, 0))

        # Desenhar por ordem de profundidade (quem está mais abaixo fica à frente)
        proxima = self.estacao_proxima() if self.estado == JOGANDO else None
        for ent in sorted([*self.estacoes, self.player], key=lambda e: e.base):
            if ent is self.player:
                ent.desenhar(self.ecra)
            else:
                ent.desenhar(self.ecra, self.fonte, ent is proxima)

        # Vinheta: bordas escuras por cima da sala, como se só o centro estivesse iluminado
        self.ecra.blit(self.vinheta, (0, 0))

        if proxima:
            aviso = self.fonte_media.render(f"[E] Interagir com {proxima.nome}", False, AMARELO)
            caixa = aviso.get_rect(midbottom=(LARGURA // 2, ALTURA - 8)).inflate(16, 8)
            pygame.draw.rect(self.ecra, PRETO, caixa)
            pygame.draw.rect(self.ecra, AMARELO, caixa, 1)
            self.ecra.blit(aviso, aviso.get_rect(center=caixa.center))

    def desenhar_caixa(self, titulo, linhas, rodape, cor_titulo=AMARELO, caixa=None):
        """`linhas` aceita strings ou tuplos (texto, cor). `caixa` permite outra posição."""
        sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
        sombra.fill((0, 0, 0, 170))
        self.ecra.blit(sombra, (0, 0))

        if caixa is None:
            caixa = pygame.Rect(0, 0, 600, 260)
            caixa.center = (LARGURA // 2, ALTURA // 2)
        pygame.draw.rect(self.ecra, PRETO, caixa)
        pygame.draw.rect(self.ecra, BRANCO, caixa, 3)

        t = self.fonte_grande.render(titulo, False, cor_titulo)
        self.ecra.blit(t, t.get_rect(midtop=(caixa.centerx, caixa.top + 20)))

        y = caixa.top + 80
        for linha in linhas:
            texto, cor = linha if isinstance(linha, tuple) else (linha, BRANCO)
            for parte in self.quebrar_texto(texto, caixa.width - 40):
                s = self.fonte_media.render(parte, False, cor)
                self.ecra.blit(s, (caixa.left + 20, y))
                y += 28
            y += 6

        r = self.fonte.render(rodape, False, CINZENTO)
        self.ecra.blit(r, r.get_rect(midbottom=(caixa.centerx, caixa.bottom - 14)))

    def quebrar_texto(self, texto, largura_max, fonte=None):
        fonte = fonte or self.fonte_media
        palavras, linhas, atual = texto.split(), [], ""
        for p in palavras:
            teste = f"{atual} {p}".strip()
            if fonte.size(teste)[0] <= largura_max:
                atual = teste
            else:
                linhas.append(atual)
                atual = p
        if atual:
            linhas.append(atual)
        return linhas

    # --- menu inicial e instruções (desenho) -----------------------------
    def criar_fundos_menu(self):
        """
        Fundo do menu: a própria sala, desfocada e muito escura, com fitas de
        "cena do crime" nos cantos. As instruções usam a mesma sala, sem fitas.
        """
        base = pygame.transform.smoothscale(self.cenario, (LARGURA // 4, ALTURA // 4))
        base = pygame.transform.smoothscale(base, (LARGURA, ALTURA))
        base.fill((90, 80, 85), special_flags=pygame.BLEND_RGB_MULT)
        luz = criar_luz(700, 460, (50, 22, 12))  # brilho avermelhado atrás do título
        base.blit(luz, luz.get_rect(center=(LARGURA // 2, 200)), special_flags=pygame.BLEND_RGB_ADD)
        base.blit(self.vinheta, (0, 0))
        base.blit(self.vinheta, (0, 0))

        instrucoes = base.copy()

        fonte_fita = pygame.font.Font(None, 22)
        texto = fonte_fita.render("CENA DO CRIME  -  NÃO ULTRAPASSE  -  ", True, (18, 16, 12))
        fita = pygame.Surface((1100, 28), pygame.SRCALPHA)
        fita.fill((222, 184, 40))
        for x in range(0, fita.get_width(), texto.get_width()):
            fita.blit(texto, (x, 7))
        pygame.draw.line(fita, (60, 48, 10), (0, 1), (fita.get_width(), 1), 2)
        pygame.draw.line(fita, (60, 48, 10), (0, 26), (fita.get_width(), 26), 2)
        for angulo, centro in ((28, (60, 70)), (24, (760, 560))):
            rodada = pygame.transform.rotozoom(fita, angulo, 1)
            sombra = rodada.copy()
            sombra.fill((0, 0, 0, 140), special_flags=pygame.BLEND_RGBA_MULT)
            base.blit(sombra, sombra.get_rect(center=(centro[0] + 4, centro[1] + 6)))
            base.blit(rodada, rodada.get_rect(center=centro))
        return base, instrucoes

    def tremeluzir(self):
        """Fator 0..1 de 'lâmpada a falhar' para o menu (determinístico no tempo)."""
        t = self.relogio_anim
        f = 0.9 + 0.06 * math.sin(t * 2.3) + 0.04 * math.sin(t * 13.7)
        if int(t * 8) % 41 in (0, 2):  # piscadelas ocasionais
            f -= 0.45
        return max(0.0, min(1.0, f))

    def texto_com_sombra(self, fonte, texto, cor, centro, sombra=(0, 0, 0), desvio=3):
        s = fonte.render(texto, True, sombra)
        self.ecra.blit(s, s.get_rect(center=(centro[0] + desvio, centro[1] + desvio)))
        t = fonte.render(texto, True, cor)
        self.ecra.blit(t, t.get_rect(center=centro))

    def desenhar_tela_inicial(self):
        self.ecra.blit(self.fundo_menu, (0, 0))
        f = self.tremeluzir()

        # Título
        self.texto_com_sombra(self.fonte_media, "ESCAPE ROOM", (200, 190, 160), (LARGURA // 2, 118), desvio=2)
        vermelho = (int(120 + 100 * f), int(14 + 16 * f), int(14 + 16 * f))
        self.texto_com_sombra(self.fonte_titulo, "ASSASSINO", vermelho, (LARGURA // 2, 175), (25, 0, 0), 4)
        self.texto_com_sombra(self.fonte_titulo, "À SOLTA", vermelho, (LARGURA // 2, 240), (25, 0, 0), 4)
        linha = self.fonte_pequena.render(
            "Arquivo confidencial  ·  Descubra o culpado antes que ele fuja", True, (150, 145, 135))
        self.ecra.blit(linha, linha.get_rect(center=(LARGURA // 2, 290)))
        pygame.draw.line(self.ecra, (110, 30, 30), (LARGURA // 2 - 180, 306), (LARGURA // 2 + 180, 306))

        # Opções
        for i, (r, nome) in enumerate(zip(self.botoes_menu(), self.OPCOES_MENU)):
            selecionado = i == self.opcao_menu
            pygame.draw.rect(self.ecra, (0, 0, 0), r.move(4, 4))
            pygame.draw.rect(self.ecra, (58, 14, 14) if selecionado else (16, 15, 20), r)
            pygame.draw.rect(self.ecra, AMARELO if selecionado else (70, 66, 80), r, 2)
            texto = f">  {nome}  <" if selecionado else nome
            cor = AMARELO if selecionado else (200, 200, 205)
            t = self.fonte_grande.render(texto, True, cor)
            self.ecra.blit(t, t.get_rect(center=r.center))

        # Rodapé: controles e estado da ligação ao Arduino
        ajuda = self.fonte_pequena.render(
            "[W/S ou setas] Navegar    [ENTER ou clique] Selecionar    [ESC] Sair", True, CINZENTO)
        self.ecra.blit(ajuda, ajuda.get_rect(midbottom=(LARGURA // 2, ALTURA - 40)))
        if self.serial.ligada:
            estado, cor = f"Arduino ligado em {self.serial.porta}", VERDE
        else:
            estado, cor = "Arduino não ligado (modo offline: F9 simula vitórias)", (200, 110, 80)
        s = self.fonte_pequena.render(estado, True, cor)
        self.ecra.blit(s, s.get_rect(midbottom=(LARGURA // 2, ALTURA - 18)))

        # Lâmpada a falhar: escurece o ecrã inteiro nas piscadelas
        if f < 1:
            escuro = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
            escuro.fill((0, 0, 0, int((1 - f) * 150)))
            self.ecra.blit(escuro, (0, 0))

    def desenhar_paragrafo(self, texto, fonte, cor, x, y, largura, entrelinha=None):
        """Escreve texto com quebra de linha automática; devolve o y seguinte."""
        entrelinha = entrelinha or fonte.get_linesize()
        for parte in self.quebrar_texto(texto, largura, fonte):
            self.ecra.blit(fonte.render(parte, True, cor), (x, y))
            y += entrelinha
        return y

    def desenhar_instrucoes(self):
        self.ecra.blit(self.fundo_instrucoes, (0, 0))

        self.texto_com_sombra(self.fonte_grande, "INSTRUÇÕES DO CASO", AMARELO, (LARGURA // 2, 34))

        painel = pygame.Rect(20, 60, LARGURA - 40, 482)
        fundo = pygame.Surface(painel.size, pygame.SRCALPHA)
        fundo.fill((10, 9, 13, 225))
        self.ecra.blit(fundo, painel)
        pygame.draw.rect(self.ecra, (110, 30, 30), painel, 2)
        divisao = painel.left + 262
        pygame.draw.line(self.ecra, (60, 56, 70), (divisao, painel.top + 14), (divisao, painel.bottom - 14))

        titulo_secao = (230, 180, 70)
        texto_cor = (215, 212, 205)

        # --- coluna da esquerda: controles e regras ---
        x, y, largura = painel.left + 18, painel.top + 14, divisao - painel.left - 32
        self.ecra.blit(self.fonte_media.render("CONTROLES", True, titulo_secao), (x, y))
        y += 30
        for tecla, acao in (("W A S D", "Andar pela sala"),
                            ("E", "Interagir com um objeto"),
                            ("ENTER", "Confirmar"),
                            ("ESC", "Voltar / cancelar")):
            t = self.fonte_pequena.render(tecla, True, (20, 18, 14))
            caixa = pygame.Rect(x, y, max(30, t.get_width() + 12), 20)
            pygame.draw.rect(self.ecra, (205, 200, 185), caixa, border_radius=3)
            pygame.draw.rect(self.ecra, (90, 86, 80), caixa, 1, border_radius=3)
            self.ecra.blit(t, t.get_rect(center=caixa.center))
            self.ecra.blit(self.fonte_pequena.render(acao, True, texto_cor), (x + 82, y + 3))
            y += 27

        y += 12
        self.ecra.blit(self.fonte_media.render("REGRAS", True, titulo_secao), (x, y))
        y += 30
        for regra in ("Você tem 12 minutos para descobrir o assassino e escapar da sala.",
                      "Cada erro num minigame tira 30 segundos do relógio.",
                      "Com 3 erros, ou se o tempo acabar, o assassino foge: fim de jogo!",
                      "O tempo restante aparece no LCD depois de sintonizar o rádio.",
                      "Cada minigame vencido revela uma pista sobre o crime."):
            pygame.draw.rect(self.ecra, VERMELHO, (x, y + 5, 5, 5))
            y = self.desenhar_paragrafo(regra, self.fonte_pequena, texto_cor, x + 12, y, largura - 12) + 6

        # --- coluna da direita: os 4 minigames ---
        x, y = divisao + 18, painel.top + 14
        largura = painel.right - x - 18
        self.ecra.blit(self.fonte_media.render("MINIGAMES", True, titulo_secao), (x, y))
        y += 30
        minigames = (
            ("Radio", "1. Rádio (Potenciômetro)",
             "Gire o potenciômetro devagar até a estática do buzzer sumir. Com o rádio "
             "sintonizado, o LCD acende com o tempo restante."),
            ("Genius", "2. Sequência de LEDs",
             "Observe a ordem em que os 4 LEDs acendem e repita-a nos botões coloridos; "
             "aperte CONFIRMA para validar. São 4 rounds e cada erro volta ao round 1."),
            ("Telegrafo", "3. Código Morse (Telégrafo)",
             "Um botão faz ponto (.) e o outro traço (-). Aperte os dois juntos para fechar "
             "a letra; com a letra vazia, os dois juntos enviam a palavra. Transmita a arma do crime."),
            ("Telefone", "4. Telefone (Discagem)",
             "Disque o número da polícia e aperte #. Depois escreva o nome do assassino no "
             "teclado T9 e aperte # (* apaga). Acusar a pessoa errada é derrota imediata!"),
        )
        for chave, nome, descricao in minigames:
            cor = MINIGAMES[chave]["cor"]
            pygame.draw.rect(self.ecra, cor, (x, y + 2, 4, 16))
            self.ecra.blit(self.fonte_media.render(nome, True, cor), (x + 12, y))
            y += 24
            y = self.desenhar_paragrafo(descricao, self.fonte_pequena, texto_cor, x + 12, y, largura - 12)
            y += 12

        # Botão voltar
        r = self.botao_voltar()
        sobre = r.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.ecra, (58, 14, 14) if sobre else (16, 15, 20), r)
        pygame.draw.rect(self.ecra, AMARELO, r, 2)
        t = self.fonte_media.render("[ESC]  Voltar ao menu", True, AMARELO)
        self.ecra.blit(t, t.get_rect(center=r.center))

    def desenhar(self):
        if self.estado == TELA_INICIAL:
            self.desenhar_tela_inicial()
            pygame.display.flip()
            return
        if self.estado == INSTRUCOES:
            self.desenhar_instrucoes()
            pygame.display.flip()
            return

        self.desenhar_mapa()
        if self.estado == MENU:
            dados = MINIGAMES[self.minigame_atual]
            self.desenhar_caixa(
                self.minigame_atual,
                [dados["descricao"], f"Hardware: {dados['hardware']}", "Iniciar o minigame físico?"],
                "[ENTER] Iniciar    [ESC] Cancelar",
            )
        elif self.estado == AGUARDANDO:
            dados = MINIGAMES[self.minigame_atual]
            pontos = "." * (int(self.tempo_aguardando * 2) % 4)
            if self.serial.ligada:
                info = f"Ligado a {self.serial.porta}. Enviado '{dados['id']}'."
            else:
                info = "Sem ligação Serial (modo offline)."
            linhas = [f"Resolva o desafio no hardware{pontos}", (info, CINZENTO)]
            if self.ultima_msg:
                linhas.append((f"> {self.ultima_msg}", VERDE))
            caixa = None
            if dados["id"] == "T":
                # Discagem: caixa de status mais abaixo, cartazes dos suspeitos por cima
                caixa = pygame.Rect(0, 0, 600, 260)
                caixa.midbottom = (LARGURA // 2, ALTURA - 20)
            self.desenhar_caixa(
                f"{self.minigame_atual} em curso",
                linhas,
                "[F9] Simular vitória (teste)    [ESC] Desistir",
                caixa=caixa,
            )
            if dados["id"] == "T":
                self.desenhar_suspeitos(caixa.top - 14)
        elif self.estado == DICA:
            self.desenhar_caixa(
                f"Dica - {self.minigame_atual}",
                [MINIGAMES[self.minigame_atual]["dica"]],
                "[ENTER] Voltar",
            )
        elif self.estado == DERROTA:
            self.desenhar_derrota()
        elif self.estado == VITORIA:
            self.desenhar_vitoria()
        pygame.display.flip()

    def desenhar_suspeitos(self, base):
        """Os 4 cartazes de procurados lado a lado, alinhados por baixo em `base`."""
        espaco = 14
        total = sum(c.get_width() for c in self.cartazes_grandes) + espaco * (len(self.cartazes_grandes) - 1)
        x = (LARGURA - total) // 2
        for cartaz in self.cartazes_grandes:
            r = cartaz.get_rect(bottomleft=(x, base))
            sombra = pygame.Surface(r.size, pygame.SRCALPHA)
            sombra.fill((0, 0, 0, 140))
            self.ecra.blit(sombra, r.move(4, 4))
            self.ecra.blit(cartaz, r)
            x += r.width + espaco

    def desenhar_derrota(self):
        """Ecrã de derrota: o mago cai no chão (anima e fica no último frame)."""
        sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
        sombra.fill((30, 0, 0, 200))
        self.ecra.blit(sombra, (0, 0))

        caixa = pygame.Rect(0, 0, 640, 440)
        caixa.center = (LARGURA // 2, ALTURA // 2)
        pygame.draw.rect(self.ecra, PRETO, caixa)
        pygame.draw.rect(self.ecra, VERMELHO, caixa, 4)

        titulo = self.fonte_titulo.render("DERROTA", False, VERMELHO)
        self.ecra.blit(titulo, titulo.get_rect(midtop=(caixa.centerx, caixa.top + 20)))

        # "Palco": um pedaço do chão da sala, para o mago escuro se destacar do preto
        palco = pygame.Rect(0, 0, 256, 176)
        palco.midtop = (caixa.centerx, caixa.top + 96)
        # (zona livre do chão, entre as armas decorativas)
        self.ecra.blit(self.cenario, palco, area=pygame.Rect(272, 294, 256, 176))
        pygame.draw.rect(self.ecra, PAREDE_BORDA, palco, 2)

        # Mago a morrer, com uma poça de sangue sob ele
        chao = (palco.centerx, palco.top + 112)
        poca = pygame.Surface((120, 26), pygame.SRCALPHA)
        pygame.draw.ellipse(poca, (120, 0, 0, 170), poca.get_rect())
        self.ecra.blit(poca, poca.get_rect(center=(chao[0], chao[1] + 14)))
        self.player.desenhar_morte(self.ecra, chao)

        y = palco.bottom + 18
        for texto, cor in (("O assassino escapou...", AMARELO),
                           ("O tempo acabou, cometeu 3 erros ou acusou a pessoa errada.", BRANCO)):
            s = self.fonte_media.render(texto, False, cor)
            self.ecra.blit(s, s.get_rect(midtop=(caixa.centerx, y)))
            y += 34

        r = self.fonte.render("[ENTER/ESC] Sair", False, CINZENTO)
        self.ecra.blit(r, r.get_rect(midbottom=(caixa.centerx, caixa.bottom - 18)))

    def desenhar_vitoria(self):
        """Ecrã final de vitória: cobre o mapa inteiro e encerra a partida."""
        sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
        sombra.fill((0, 20, 8, 225))
        self.ecra.blit(sombra, (0, 0))

        caixa = pygame.Rect(0, 0, 660, 380)
        caixa.center = (LARGURA // 2, ALTURA // 2)
        pygame.draw.rect(self.ecra, PRETO, caixa)
        pygame.draw.rect(self.ecra, VERDE, caixa, 4)
        pygame.draw.rect(self.ecra, AMARELO, caixa.inflate(-14, -14), 1)

        titulo = self.fonte_titulo.render("VITÓRIA!", False, VERDE)
        self.ecra.blit(titulo, titulo.get_rect(midtop=(caixa.centerx, caixa.top + 30)))

        linhas = [
            ("Parabéns, detetive!", AMARELO),
            ("Descobriu o assassino e ele foi preso.", BRANCO),
            ("A porta destrancou-se e escapou da sala a tempo.", BRANCO),
            ("Fim da partida.", CINZENTO),
        ]
        y = caixa.top + 130
        for texto, cor in linhas:
            s = self.fonte_media.render(texto, False, cor)
            self.ecra.blit(s, s.get_rect(midtop=(caixa.centerx, y)))
            y += 40

        r = self.fonte.render("[ENTER/ESC] Sair", False, CINZENTO)
        self.ecra.blit(r, r.get_rect(midbottom=(caixa.centerx, caixa.bottom - 18)))

    # --- loop principal ---------------------------------------------------
    def executar(self):
        while self.a_correr:
            dt = self.relogio.tick(FPS) / 1000.0
            self.tratar_eventos()
            self.atualizar(dt)
            self.desenhar()
        self.serial.fechar()
        pygame.quit()


if __name__ == "__main__":
    Jogo().executar()
    sys.exit()
