"""
Escape Room estilo FNAF - Front-end (Pygame CE)

Máquina de estados não-bloqueante:
    JOGANDO -> movimento livre pelo mapa; aproximar-se de uma estação e premir E abre o MENU
    MENU       -> confirmação para iniciar o minigame físico (ENTER = sim, ESC = não)
    AGUARDANDO -> envia o ID do minigame por Serial e lê a porta (sem bloquear) até
                  receber "WIN_<ID>" do Arduino
    DICA       -> mostra a mensagem de recompensa do minigame (ENTER/ESC para voltar)

Controlos: WASD para mover, E para interagir.
Cheat de teste: F9 no estado AGUARDANDO simula a vitória.
"""

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
PORTA_SERIAL = "COM3"
BAUDRATE = 9600

# Estados
JOGANDO = "JOGANDO"
MENU = "MENU"
AGUARDANDO = "AGUARDANDO"
DICA = "DICA"

# Cores
PRETO = (10, 10, 14)
CHAO = (28, 26, 34)
GRELHA = (36, 34, 44)
BRANCO = (230, 230, 230)
VERMELHO = (200, 30, 30)
AMARELO = (240, 200, 60)
CINZENTO = (120, 120, 130)
VERDE = (60, 200, 90)

# ---------------------------------------------------------------------------
# Minigames e respetivas dicas
# ---------------------------------------------------------------------------
MINIGAMES = {
    "Radio": {
        "id": "R",
        "descricao": "Sintonize a frequência certa com o potenciómetro. Siga o buzzer.",
        "hardware": "Potenciómetro + Buzzer",
        "dica": "Uma voz no meio da estática: 'O assassino nunca sai sem o casaco.'",
        "pos": (120, 120),
        "cor": (90, 160, 220),
    },
    "Genius": {
        "id": "G",
        "descricao": "Repita a sequência de luzes nos 4 LEDs sem errar.",
        "hardware": "4 LEDs + 4 botões",
        "dica": "As luzes piscam um padrão: o assassino estava na sala às 3h00.",
        "pos": (680, 120),
        "cor": (220, 160, 60),
    },
    "Telegrafo": {
        "id": "M",
        "descricao": "Transmita a mensagem correta em código Morse.",
        "hardware": "Botão de telégrafo (Morse)",
        "dica": "O telégrafo responde: '... .- -... .' - o nome tem 4 letras.",
        "pos": (120, 480),
        "cor": (170, 100, 220),
    },
    "Telefone": {
        "id": "T",
        "descricao": "Marque o nome do assassino no teclado T9 do telefone.",
        "hardware": "Teclado matricial (T9)",
        "dica": "A linha cai... Se o nome estiver certo, a porta destranca!",
        "pos": (680, 480),
        "cor": (80, 200, 140),
    },
}

TAMANHO_ESTACAO = 48
RAIO_INTERACAO = 70


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
        self.buffer = ""
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
                self.buffer += self.ser.read(n).decode("ascii", errors="ignore")
        except serial.SerialException as e:
            self._falha(e)
            return []

        *linhas, self.buffer = self.buffer.replace("\r", "").split("\n")
        return [l.strip() for l in linhas if l.strip()]

    def limpar_entrada(self):
        """Descarta dados antigos (ex.: lixo do reset do Arduino) antes de um novo minigame."""
        self.buffer = ""
        if self.ligada:
            try:
                self.ser.reset_input_buffer()
            except serial.SerialException as e:
                self._falha(e)

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
# Entidades
# ---------------------------------------------------------------------------
class Player:
    """Jogador provisório: quadrado vermelho que se move com WASD."""

    def __init__(self, x, y, tamanho=28, velocidade=220):
        self.rect = pygame.Rect(0, 0, tamanho, tamanho)
        self.rect.center = (x, y)
        self.velocidade = velocidade  # píxeis por segundo
        # posição em float para movimento suave independente do FPS
        self.x, self.y = float(self.rect.x), float(self.rect.y)

    def atualizar(self, dt, teclas):
        dx = (teclas[pygame.K_d] - teclas[pygame.K_a])
        dy = (teclas[pygame.K_s] - teclas[pygame.K_w])
        if dx and dy:  # normalizar diagonal
            dx *= 0.7071
            dy *= 0.7071

        self.x += dx * self.velocidade * dt
        self.y += dy * self.velocidade * dt

        # Limitar aos limites do ecrã
        self.x = max(0, min(self.x, LARGURA - self.rect.width))
        self.y = max(0, min(self.y, ALTURA - self.rect.height))
        self.rect.topleft = (round(self.x), round(self.y))

    def desenhar(self, ecra):
        pygame.draw.rect(ecra, VERMELHO, self.rect)
        pygame.draw.rect(ecra, PRETO, self.rect, 2)


class Estacao:
    """Ponto do mapa onde se inicia um minigame físico."""

    def __init__(self, nome, dados):
        self.nome = nome
        self.dados = dados
        self.rect = pygame.Rect(0, 0, TAMANHO_ESTACAO, TAMANHO_ESTACAO)
        self.rect.center = dados["pos"]
        self.concluido = False

    def perto_de(self, player):
        dx = player.rect.centerx - self.rect.centerx
        dy = player.rect.centery - self.rect.centery
        return dx * dx + dy * dy <= RAIO_INTERACAO ** 2

    def desenhar(self, ecra, fonte, destacado):
        cor = CINZENTO if self.concluido else self.dados["cor"]
        pygame.draw.rect(ecra, cor, self.rect)
        pygame.draw.rect(ecra, AMARELO if destacado else PRETO, self.rect, 3)
        txt = fonte.render(self.nome, False, BRANCO)
        ecra.blit(txt, txt.get_rect(midtop=(self.rect.centerx, self.rect.bottom + 4)))
        if self.concluido:
            ok = fonte.render("OK", False, VERDE)
            ecra.blit(ok, ok.get_rect(center=self.rect.center))


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

        self.player = Player(LARGURA // 2, ALTURA // 2)
        self.estacoes = [Estacao(nome, dados) for nome, dados in MINIGAMES.items()]

        self.serial = ConexaoSerial(PORTA_SERIAL, BAUDRATE)
        if self.serial.ligada:
            print(f"[Serial] Ligado a {PORTA_SERIAL} @ {BAUDRATE}")
        else:
            print(f"[Serial] Modo offline ({self.serial.erro}). Use F9 para simular vitórias.")

        self.estado = JOGANDO
        self.minigame_atual = None  # nome do minigame selecionado
        self.tempo_aguardando = 0.0
        self.a_correr = True

    # --- transições de estado -------------------------------------------
    def mudar_estado(self, novo, minigame=None):
        self.estado = novo
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
        self.serial.limpar_entrada()
        if self.serial.enviar(ident):
            print(f"[Serial] Enviado: {ident}")
        self.tempo_aguardando = 0.0
        self.mudar_estado(AGUARDANDO, nome)

    def vitoria(self, nome):
        """Minigame concluído: marca a estação e mostra a dica."""
        for est in self.estacoes:
            if est.nome == nome:
                est.concluido = True
        self.mudar_estado(DICA, nome)

    def verificar_serial(self):
        """Chamado a cada frame em AGUARDANDO: lê só o que já chegou e regressa logo."""
        esperado = "WIN_" + MINIGAMES[self.minigame_atual]["id"]
        for linha in self.serial.ler_linhas():
            print(f"[Serial] Recebido: {linha}")
            if linha == esperado:
                self.vitoria(self.minigame_atual)
                return

    # --- eventos ----------------------------------------------------------
    def tratar_eventos(self):
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                self.a_correr = False
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
                        self.vitoria(self.minigame_atual)
                    elif evento.key == pygame.K_ESCAPE:  # desistir e voltar ao mapa
                        self.mudar_estado(JOGANDO)

                elif self.estado == DICA:
                    if evento.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_ESCAPE):
                        self.mudar_estado(JOGANDO)

    # --- lógica -----------------------------------------------------------
    def atualizar(self, dt):
        if self.estado == JOGANDO:
            self.player.atualizar(dt, pygame.key.get_pressed())
        elif self.estado == AGUARDANDO:
            self.tempo_aguardando += dt
            self.verificar_serial()

    # --- desenho ----------------------------------------------------------
    def desenhar_mapa(self):
        self.ecra.fill(CHAO)
        for x in range(0, LARGURA, 32):
            pygame.draw.line(self.ecra, GRELHA, (x, 0), (x, ALTURA))
        for y in range(0, ALTURA, 32):
            pygame.draw.line(self.ecra, GRELHA, (0, y), (LARGURA, y))

        proxima = self.estacao_proxima() if self.estado == JOGANDO else None
        for est in self.estacoes:
            est.desenhar(self.ecra, self.fonte, est is proxima)
        self.player.desenhar(self.ecra)

        if proxima:
            aviso = self.fonte_media.render(f"[E] Interagir com {proxima.nome}", False, AMARELO)
            self.ecra.blit(aviso, aviso.get_rect(midbottom=(LARGURA // 2, ALTURA - 12)))

    def desenhar_caixa(self, titulo, linhas, rodape):
        sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
        sombra.fill((0, 0, 0, 170))
        self.ecra.blit(sombra, (0, 0))

        caixa = pygame.Rect(0, 0, 600, 260)
        caixa.center = (LARGURA // 2, ALTURA // 2)
        pygame.draw.rect(self.ecra, PRETO, caixa)
        pygame.draw.rect(self.ecra, BRANCO, caixa, 3)

        t = self.fonte_grande.render(titulo, False, AMARELO)
        self.ecra.blit(t, t.get_rect(midtop=(caixa.centerx, caixa.top + 20)))

        y = caixa.top + 80
        for linha in linhas:
            for parte in self.quebrar_texto(linha, caixa.width - 40):
                s = self.fonte_media.render(parte, False, BRANCO)
                self.ecra.blit(s, (caixa.left + 20, y))
                y += 28
            y += 6

        r = self.fonte.render(rodape, False, CINZENTO)
        self.ecra.blit(r, r.get_rect(midbottom=(caixa.centerx, caixa.bottom - 14)))

    def quebrar_texto(self, texto, largura_max):
        palavras, linhas, atual = texto.split(), [], ""
        for p in palavras:
            teste = f"{atual} {p}".strip()
            if self.fonte_media.size(teste)[0] <= largura_max:
                atual = teste
            else:
                linhas.append(atual)
                atual = p
        if atual:
            linhas.append(atual)
        return linhas

    def desenhar(self):
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
            self.desenhar_caixa(
                f"{self.minigame_atual} em curso",
                [f"Resolva o desafio no hardware{pontos}", info],
                "[F9] Simular vitória (teste)    [ESC] Desistir",
            )
        elif self.estado == DICA:
            self.desenhar_caixa(
                f"Dica - {self.minigame_atual}",
                [MINIGAMES[self.minigame_atual]["dica"]],
                "[ENTER] Voltar",
            )
        pygame.display.flip()

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
