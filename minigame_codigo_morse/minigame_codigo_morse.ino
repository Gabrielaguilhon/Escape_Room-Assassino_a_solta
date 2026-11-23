#include <avr/io.h>
#include <avr/interrupt.h>

// Macros pra mexer nos bits dos registradores mais facil
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))

// Controle geral do jogo (tempo, penalidades e contagem de erros)
uint32_t tempo_total = 12UL * 60UL * 1000UL; // 12 minutos em ms
uint32_t penalidade_acumulada = 0;
uint8_t erros = 0;
const uint8_t MAX_ERROS = 3;

// Estados possiveis do minigame
enum Estado { MORSE, VITORIA, DERROTA };
Estado estado_atual = MORSE;

// Variaveis pra montar a palavra em codigo morse
String letraAtual = "";
String senhaDigitada = "";
String senhaCorreta = "..-. .- -.-. .- "; // FACA

// Controle de debounce e leitura dos botoes
uint32_t tempoUltimaLeitura = 0;
const uint32_t tempoDebounce = 50;
uint8_t estadoAnterior = 0;
uint8_t estadoMaximo = 0; // guarda se os dois botoes chegaram a ser apertados juntos

// Contador de milissegundos atualizado na interrupcao do Timer1
volatile uint32_t ms = 0;

ISR(TIMER1_COMPA_vect) {
  ms++;
}

// Le o valor de ms pausando as interrupcoes rapidinho pra nao corromper o dado
uint32_t meu_millis() {
  uint32_t tempo;
  cli();
  tempo = ms;
  sei();
  return tempo;
}

// Converte o tempo que ainda falta de ms para MM:SS e mostra no monitor serial
void mostrar_tempo_restante(uint32_t tempo_atual) {
  if (tempo_atual >= tempo_total) {
    Serial.println("Tempo Restante: 00:00");
    return;
  }

  uint32_t tempo_restante_ms = tempo_total - tempo_atual;
  uint32_t segundos_totais = tempo_restante_ms / 1000;
  uint8_t minutos = segundos_totais / 60;
  uint8_t segundos = segundos_totais % 60;

  Serial.print("Tempo Restante: ");
  Serial.print(minutos);
  Serial.print(":");
  if (segundos < 10) {
    Serial.print("0"); // coloca o zero na frente pra ficar tipo 09 em vez de 9
  }
  Serial.println(segundos);
}

// Soma um erro e tira 30 segundos do relogio toda vez que o jogador erra
void registrar_erro(uint32_t tempo_atual) {
  erros++;
  penalidade_acumulada += 30000;

  // Evita dar underflow caso falte menos de 30s no relogio
  if (tempo_total >= 30000) {
    tempo_total -= 30000;
  } else {
    tempo_total = 0;
  }

  Serial.print("--- ARMA ERRADA! Penalidade de 30s aplicada. Erros: ");
  Serial.print(erros);
  Serial.print("/");
  Serial.println(MAX_ERROS);
  mostrar_tempo_restante(tempo_atual);
}

// Leitura do ADC com dummy read pra evitar ghosting entre os canais
uint16_t ler_adc(uint8_t canal) {
  ADMUX = (ADMUX & 0xF0) | canal;

  // Primeira conversao descartada
  set_bit(ADCSRA, ADSC);
  while (tst_bit(ADCSRA, ADSC));

  // Segunda conversao (leitura valida)
  set_bit(ADCSRA, ADSC);
  while (tst_bit(ADCSRA, ADSC));

  return ADC;
}

//Funcao para substituir delay
void meu_delay(uint32_t tempo_espera) {
    uint32_t inicio = meu_millis();
    while (meu_millis() - inicio < tempo_espera) {
        // Fica preso aqui até o tempo passar, usando o seu Timer 1
    }
}

void setup() {
  Serial.begin(9600);

  cli(); // desliga interrupcoes enquanto configura o hardware

  // Configura o Timer1 em modo CTC para disparar a cada 1ms (prescaler 64)
  TCCR1A = 0;
  TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10);
  OCR1A = 249;
  TIMSK1 = (1 << OCIE1A);

  // A1 (PC1) como entrada com pull-up pro botao de ponto
  clr_bit(DDRC, PC1);
  set_bit(PORTC, PC1);

  // A2 (PC2) como entrada com pull-up pro botao de traco
  clr_bit(DDRC, PC2);
  set_bit(PORTC, PC2);

  // Liga o ADC com referencia AVcc e prescaler 128
  ADMUX = (1 << REFS0);
  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);

  sei(); // religa interrupcoes

  Serial.println("Minigame Codigo Morse iniciado");
  mostrar_tempo_restante(0);
  Serial.println("Digite a arma do crime!");
  meu_delay(200);
}

void loop() {
  uint32_t tempoAtual = meu_millis();

  // Antes de tudo, checa se o jogador ja perdeu por tempo ou por limite de erros
  if (estado_atual != DERROTA && estado_atual != VITORIA) {
    if (tempoAtual >= tempo_total) {
      estado_atual = DERROTA;
      Serial.println("\n--- O TEMPO ACABOU! FIM DE JOGO ---");
    } else if (erros >= MAX_ERROS) {
      estado_atual = DERROTA;
      Serial.println("\n--- LIMITE DE 3 ERROS ATINGIDO! FIM DE JOGO ---");
    }
  }

  switch (estado_atual) {
    case MORSE:
      // So le os botoes respeitando o intervalo de debounce
      if (tempoAtual - tempoUltimaLeitura >= tempoDebounce) {
        tempoUltimaLeitura = tempoAtual;

        // Como os botoes tem pull-up, apertado da valor baixo no ADC (< 512)
        bool btnPonto = (ler_adc(1) < 512);
        bool btnTraco = (ler_adc(2) < 512);

        // Mapeia qual combinacao esta apertada agora: 1=ponto, 2=traco, 3=ambos
        uint8_t estadoAtual = 0;
        if (btnPonto && btnTraco) estadoAtual = 3;
        else if (btnPonto) estadoAtual = 1;
        else if (btnTraco) estadoAtual = 2;

        // Guarda o "maior" estado enquanto os botoes estao pressionados
        // Assim, se o usuario apertou os dois juntos (3), soltar um antes do outro nao conta como clique individual
        if (estadoAtual != 0) {
          if (estadoAtual == 3) {
            estadoMaximo = 3;
          } else if (estadoMaximo != 3) {
            estadoMaximo = estadoAtual;
          }
        }

        // Borda de descida: so executa a acao quando o jogador solta tudo
        if (estadoAtual == 0 && estadoAnterior != 0) {

          // Os dois botoes juntos servem pra confirmar a letra ou enviar a senha inteira
          if (estadoMaximo == 3) {
            if (letraAtual != "") {
              // Fecha a letra atual e joga na palavra
              Serial.println();
              Serial.print("Letra confirmada: ");
              Serial.println(letraAtual);

              senhaDigitada += letraAtual + " ";

              Serial.print("Palavra atual (em Morse): ");
              Serial.println(senhaDigitada);

              letraAtual = "";
            }
            else if (senhaDigitada != "") {
              // Se nao tinha letra pendente, apertar os dois de novo valida a senha completa
              Serial.println();
              Serial.println(">>> VERIFICANDO SENHA <<<");

              if (senhaDigitada == senhaCorreta) {
                Serial.println("===============================");
                Serial.println("\nMini-game concluido!\nDica desbloqueada: Foi encontrado um FIO DE CABELO RUIVO na cena do crime!\n");
                mostrar_tempo_restante(tempoAtual);
                Serial.println("===============================");
                estado_atual = VITORIA;
              } else {
                // Errou a palavra: aplica penalidade e limpa pra tentar de novo
                registrar_erro(tempoAtual);
                senhaDigitada = "";
              }
            }
          }
          // Botao da esquerda adiciona ponto
          else if (estadoMaximo == 1) {
            letraAtual += ".";
            Serial.print(".");
          }
          // Botao da direita adiciona traco
          else if (estadoMaximo == 2) {
            letraAtual += "-";
            Serial.print("-");
          }

          estadoMaximo = 0; // reseta pro proximo clique
        }

        estadoAnterior = estadoAtual;
      }
      break;

    case VITORIA:
      // Minigame concluido, fica parado aqui ate integrar com o proximo jogo
      break;

    case DERROTA:
      // Fim de jogo, trava as acoes
      break;
  }
}