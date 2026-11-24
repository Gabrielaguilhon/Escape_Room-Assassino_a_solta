#include <avr/io.h>
#include <avr/interrupt.h>
#include <stdlib.h>
#include <util/delay.h>
#include <LiquidCrystal_I2C.h>
#include <SoftwareWire.h>
#include <string.h>

// Macros obrigatórias para manipulação de bits
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))

// ==========================================
// VARIÁVEIS GERAIS E MÁQUINA DE ESTADOS
// ==========================================
volatile uint32_t ms = 0;

uint32_t tempo_total = 12UL * 60UL * 1000UL; // 12 minutos
uint32_t penalidade_acumulada = 0;
uint8_t erros = 0;
const uint8_t MAX_ERROS = 3;

// Estados principais unificados
enum Estado { MENU, RADIO, LEDS, MORSE, DISCAGEM, VITORIA, DERROTA };
Estado estado_atual = MENU;

// ==========================================
// 1. VARIÁVEIS DO MINI-GAME RÁDIO
// ==========================================
LiquidCrystal_I2C lcd(0x27, 16, 2);
#define LIMIAR_ALTO 700 // acima disso: ruídos
#define LIMIAR_BAIXO 600 // abaixo disso: ruídos
uint32_t tempo_ultimo_lcd = 0;
int radio_sintonizado = 0; // começa não sintonizado

// ==========================================
// 2. VARIÁVEIS DO MINI-GAME LEDS
// ==========================================
#define MASCARA_LEDS ((1 << PD3) | (1 << PD4) | (1 << PD5) | (1 << PD7))

volatile bool confirma_pressionado = false;
volatile uint32_t tempo_ultimo_confirma = 0;

enum SubEstadoLeds { GERAR_SEQ, MOSTRAR_SEQ, ESPERAR_JOGADOR, ESPERAR_PROXIMO_ROUND };
SubEstadoLeds estado_leds = GERAR_SEQ;

uint8_t round_atual = 1;
uint8_t sequencia[5];
uint8_t resposta_jogador[5];
uint8_t passo_seq = 0;
uint8_t passo_jogador = 0;
uint32_t tempo_led_anterior = 0;
bool led_aceso = false;
uint8_t estado_botoes_anterior = 0;

const uint8_t pinos_leds[4] = {PD7, PD3, PD5, PD4};

// ==========================================
// 3. VARIÁVEIS DO MINI-GAME CÓDIGO MORSE
// ==========================================
String letraAtual = "";
String senhaDigitada = "";
String senhaCorreta = "..-. .- -.-. .- "; // FACA

uint32_t tempoUltimaLeitura = 0;
const uint32_t tempoDebounce = 50;
uint8_t estadoAnterior = 0;
uint8_t estadoMaximo = 0;

// ==========================================
// 4. VARIÁVEIS DO MINI-GAME DISCAGEM
// ==========================================
const int SDA_PIN = 8;
const int SCL_PIN = 9;
SoftwareWire softWire(SDA_PIN, SCL_PIN);

uint32_t ultimo_toque = 0;
const uint32_t TEMPO_DEBOUNCE = 200;
const uint8_t ENDERECO_TECLADO = 0x27;

char mapaTeclas[4][3] = {
  {'1', '2', '3'},
  {'4', '5', '6'},
  {'7', '8', '9'},
  {'*', '0', '#'}
};

uint8_t bitsLinhas[4] = {0, 1, 2, 4};
uint8_t bitsColunas[3] = {5, 6, 7};

char discagem[] = "190";
char discagemRealizada[4] = "";
int indiceDiscagem = 0;
bool policiaAtendeu = false;

char senha_real[] = "166111"; // AnaB
char senha_digitada[7] = "";
int indiceSenha = 0;

// ==========================================
// INTERRUPÇÕES E FUNÇÕES COMPARTILHADAS
// ==========================================
ISR(TIMER1_COMPA_vect) {
    ms++;
}

ISR(INT0_vect) {
    if (ms - tempo_ultimo_confirma > 200) {
        confirma_pressionado = true;
        tempo_ultimo_confirma = ms;
    }
}

uint32_t meu_millis() {
    uint32_t tempo;
    cli();
    tempo = ms;
    sei();
    return tempo;
}

void meu_delay(uint32_t tempo_espera) {
    uint32_t inicio = meu_millis();
    while (meu_millis() - inicio < tempo_espera) {
        // Aguarda usando o Timer 1
    }
}

void meu_tone(uint16_t frequencia) {
    set_bit(DDRD, PD6);
    OCR0A = 62500 / frequencia - 1;
    TCCR0A = (1 << COM0A0) | (1 << WGM01);
    TCCR0B = (1 << CS01) | (1 << CS00);
}

void meu_noTone() {
    TCCR0B = 0;
    TCCR0A = 0;
    clr_bit(PORTD, PD6);
}

void mostrar_tempo_restante(uint32_t tempo_atual) {
    if (tempo_atual >= tempo_total) {
        lcd.setCursor(0, 0);
        lcd.print(F("Tempo: 00:00   "));
        return;
    }

    uint32_t tempo_restante_ms = tempo_total - tempo_atual;
    uint32_t segundos_totais = tempo_restante_ms / 1000;
    uint8_t minutos = segundos_totais / 60;
    uint8_t segundos = segundos_totais % 60;

    lcd.backlight();
    lcd.setCursor(0, 0);
    lcd.print(F("Tempo: "));
    
    // Adiciona o zero à esquerda nos minutos (ex: 09 em vez de 9)
    if (minutos < 10) {
        lcd.print(F("0"));
    }
    lcd.print(minutos);
    lcd.print(F(":"));

    // Adiciona o zero à esquerda nos segundos
    if (segundos < 10) {
        lcd.print(F("0"));
    }
    lcd.print(segundos);
    
    // Imprime espaços no final para apagar "sujeira" de números anteriores
    lcd.print(F("   ")); 
}

// ==========================================
// FUNÇÕES DO RÁDIO
// ==========================================
uint16_t meu_analogRead(uint8_t canal) {
    ADMUX = (ADMUX & 0xF0) | canal;
    set_bit(ADCSRA, ADSC);
    while (tst_bit(ADCSRA, ADSC));
    return ADC;
}

void sintoniza_radio(uint16_t valor) {
    if (valor > LIMIAR_ALTO || valor < LIMIAR_BAIXO) {
        radio_sintonizado = 0;
        uint16_t frequencia_chiado = 500 + (rand() % 2000);
        meu_tone(frequencia_chiado);
        Serial.println(F("Voce ainda nao conseguiu sintonizar o radio, esta perdendo tempo..."));
        lcd.noBacklight();
    } else {
        radio_sintonizado = 1;
        meu_noTone();
        //Serial.println(F("Sinal Radio: "));
        Serial.println(F("Radio sintonizado"));
        // Atualiza o LCD automaticamente a cada 1 segundo (1000 ms)
        
        //lcd.backlight();
        //lcd.setCursor(0, 0);
        //lcd.print(F("Está ligado"));
        Serial.println(radio_sintonizado);
        Serial.println(F("Dica: Um batom foi encontrado na cena do crime"));

        // Passa para o próximo mini-game (LEDs)
        estado_atual = LEDS;
    }
}

// ==========================================
// FUNÇÕES DOS LEDS
// ==========================================
uint8_t ler_estado_botoes() {
    uint8_t estado = 0;

    if (!tst_bit(PINC, PC1)) set_bit(estado, 0); // Botão 1 (Vermelho) -> A1
    if (!tst_bit(PINC, PC2)) set_bit(estado, 1); // Botão 2 (Amarelo)  -> A2
    if (!tst_bit(PINB, PB3)) set_bit(estado, 2); // Botão 3 (Verde)    -> 11
    if (!tst_bit(PINB, PB2)) set_bit(estado, 3); // Botão 4 (Azul)     -> 10

    return estado;
}

// ==========================================
// FUNÇÕES DO CÓDIGO MORSE
// ==========================================
void registrar_erro(uint32_t tempo_atual) {
    erros++;
    penalidade_acumulada += 30000;

    if (tempo_total >= 30000) {
        tempo_total -= 30000;
    } else {
        tempo_total = 0;
    }

    Serial.print(F("--- ARMA ERRADA! Penalidade de 30s aplicada. Erros: "));
    Serial.print(erros);
    Serial.print(F("/"));
    Serial.println((MAX_ERROS));
    mostrar_tempo_restante(tempo_atual);
}

uint16_t ler_adc(uint8_t canal) {
    ADMUX = (ADMUX & 0xF0) | canal;

    set_bit(ADCSRA, ADSC);
    while (tst_bit(ADCSRA, ADSC));

    set_bit(ADCSRA, ADSC);
    while (tst_bit(ADCSRA, ADSC));

    return ADC;
}

// ==========================================
// FUNÇÕES DA DISCAGEM
// ==========================================
void som_facada() {
    uint32_t tempo = meu_millis();
    while (tempo > 0) {
        for (int i = 0; i < 40; i++) {
            meu_tone(random(120, 950));
            meu_delay(1);
        }
        for (int freq = 220; freq >= 45; freq -= 15) {
            meu_tone(freq + random(-20, 20));
            meu_delay(4);
        }
        meu_noTone();
        meu_delay(550);
    }
}

void som_sirene() {
    for (int i = 0; i < 5; i++) {
        meu_tone(635);
        meu_delay(400);
        meu_tone(912);
        meu_delay(400);
    }
    meu_noTone();
}

char lerTeclado() {
    for (int linha = 0; linha < 4; linha++) {
        uint8_t valorEscrita = ~(1 << bitsLinhas[linha]);

        softWire.beginTransmission(ENDERECO_TECLADO);
        softWire.write(valorEscrita);
        softWire.endTransmission();

        softWire.requestFrom(ENDERECO_TECLADO, (uint8_t)1);
        if (softWire.available()) {
            uint8_t leitura = softWire.read();

            for (int coluna = 0; coluna < 3; coluna++) {
                if ((leitura & (1 << bitsColunas[coluna])) == 0) {
                    return mapaTeclas[linha][coluna];
                }
            }
        }
    }
    return '\0';
}

void guardaSenha(char tecla) {
    if (tecla != '\0') {
        Serial.print(F("Tecla pressionada: "));
        Serial.println(tecla);

        if (tecla == '#') {
            senha_digitada[indiceSenha] = '\0';

            Serial.print(F("Jogador tentou o suspeito: "));
            Serial.println(senha_digitada);

            if (strcmp(senha_digitada, senha_real) == 0) {
                Serial.println(F("ACERTOU!"));
                //som_sirene();
                estado_atual = VITORIA;
            } else {
                Serial.println(F("ERROU!"));
                //som_facada();
                estado_atual = DERROTA;
            }

            indiceSenha = 0;
            senha_digitada[0] = '\0';
        }
        else if (tecla == '*') {
            if (indiceSenha > 0) {
                indiceSenha--;
                senha_digitada[indiceSenha] = '\0';
                Serial.println(F("Apagou o ultimo digito."));
            }
        }
        else {
            if (indiceSenha < 6) {
                senha_digitada[indiceSenha] = tecla;
                indiceSenha++;
                senha_digitada[indiceSenha] = '\0';

                Serial.print(F("Senha parcial: "));
                Serial.println(senha_digitada);
            } else {
                Serial.println(F("Limite maximo de caracteres atingido!"));
            }
        }
    }
}

void discaNumero(char tecla) {
    if (tecla != '\0') {
        Serial.print(F("Tecla pressionada: "));
        Serial.println(tecla);

        if (tecla == '#') {
            discagemRealizada[indiceDiscagem] = '\0';

            if (strcmp(discagemRealizada, discagem) == 0) {
                Serial.println(F("Você foi atendido! Pode indicar o assassino."));
                policiaAtendeu = true;
            } else {
                Serial.println(F("Sua discagem está inadequada! Repita, por favor!"));
            }

            indiceDiscagem = 0;
            discagemRealizada[0] = '\0';
        }
        else if (tecla == '*') {
            if (indiceDiscagem > 0) {
                indiceDiscagem--;
                discagemRealizada[indiceDiscagem] = '\0';
                Serial.println(F("Apagou o ultimo digito."));
            }
        }
        else {
            if (indiceDiscagem < 3) {
                discagemRealizada[indiceDiscagem] = tecla;
                indiceDiscagem++;
                discagemRealizada[indiceDiscagem] = '\0';

                Serial.print(F("Discagem parcial: "));
                Serial.println(discagemRealizada);
            } else {
                Serial.println(F("Limite maximo de caracteres atingido!"));
            }
        }
    }
}

void setup() {
    Serial.begin(9600);
    lcd.init();
    softWire.begin();

    cli();

    // Timer1 para contar milissegundos
    TCCR1A = 0;
    TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10);
    OCR1A = 249;
    TIMSK1 = (1 << OCIE1A);

    // ADC (usado no Rádio e no Morse)
    ADMUX = (1 << REFS0);
    ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);

    // LEDs como SAÍDA (PD3, PD4, PD5 e PD7)
    DDRD |= MASCARA_LEDS;
    PORTD &= ~MASCARA_LEDS;

    // Botão CONFIRMA (Pino 2 / PD2 / INT0)
    clr_bit(DDRD, PD2);
    set_bit(PORTD, PD2);
    set_bit(EICRA, ISC01);
    clr_bit(EICRA, ISC00);
    set_bit(EIFR, INTF0);
    set_bit(EIMSK, INT0);

    // Entradas Analógicas A1 e A2 com Pull-up (usadas nos LEDs e no Morse)
    DDRC &= ~((1 << PC1) | (1 << PC2));
    PORTC |= (1 << PC1) | (1 << PC2);

    // Entradas Digitais Pinos 10 e 11 com Pull-up (usadas nos LEDs)
    DDRB &= ~((1 << PB2) | (1 << PB3));
    PORTB |= (1 << PB2) | (1 << PB3);

    sei();

    Serial.println(F("--- Escape Room Iniciado ---"));
    mostrar_tempo_restante(0);
    estado_atual = RADIO;
}

// ==========================================
// LOOP PRINCIPAL (MÁQUINA DE ESTADOS)
// ==========================================
void loop() {
    uint32_t tempo_atual = meu_millis();
    if (tempo_atual - tempo_ultimo_lcd >= 1000) {
        tempo_ultimo_lcd = tempo_atual;
        mostrar_tempo_restante(tempo_atual);
        }

    // Verifica condições de derrota (Tempo esgotado ou 3+ erros)
    if (estado_atual != DERROTA && estado_atual != VITORIA) {
        if (tempo_atual >= tempo_total) {
            estado_atual = DERROTA;
            Serial.println("\n--- O TEMPO ACABOU! FIM DE JOGO ---");
            PORTD &= ~MASCARA_LEDS;
        } else if (erros >= MAX_ERROS) {
            estado_atual = DERROTA;
            Serial.println("\n--- LIMITE DE 3 ERROS ATINGIDO! FIM DE JOGO ---");
            PORTD &= ~MASCARA_LEDS;
        }
    }

    switch (estado_atual) {
        case MENU: {
            break;
        }
        // 1º MINI-GAME: RÁDIO
        case RADIO: {
            uint16_t valor = meu_analogRead(0);
            sintoniza_radio(valor);
            Serial.println(valor);
            break;
        }

        // 2º MINI-GAME: SEQUÊNCIA DE LEDS
        case LEDS: {
            switch (estado_leds) {
                case ESPERAR_PROXIMO_ROUND: {
                    if (tempo_atual - tempo_led_anterior >= 1500) {
                        estado_leds = GERAR_SEQ;
                    }
                    break;
                }

                case GERAR_SEQ: {
                    uint8_t qtd_leds = round_atual + 1;
                    for (uint8_t i = 0; i < qtd_leds; i++) {
                        sequencia[i] = rand() % 4;
                    }
                    passo_seq = 0;
                    led_aceso = false;
                    tempo_led_anterior = tempo_atual;
                    estado_leds = MOSTRAR_SEQ;

                    Serial.print(F("--- ROUND "));
                    Serial.print(round_atual);
                    Serial.println(F(" ---"));
                    Serial.println(F("Atencao! Mostrando sequencia..."));
                    break;
                }

                case MOSTRAR_SEQ: {
                    uint8_t pino_led_atual = pinos_leds[sequencia[passo_seq]];
                    if (!led_aceso) {
                        if (tempo_atual - tempo_led_anterior >= 400) {
                            set_bit(PORTD, pino_led_atual);
                            led_aceso = true;
                            tempo_led_anterior = tempo_atual;
                        }
                    } else {
                        if (tempo_atual - tempo_led_anterior >= 600) {
                            clr_bit(PORTD, pino_led_atual);
                            led_aceso = false;
                            tempo_led_anterior = tempo_atual;
                            passo_seq++;

                            if (passo_seq >= (round_atual + 1)) {
                                passo_jogador = 0;
                                confirma_pressionado = false;
                                estado_botoes_anterior = ler_estado_botoes();
                                estado_leds = ESPERAR_JOGADOR;
                                Serial.println(F("Sua vez! Repita a sequencia e aperte CONFIRMA (Pino 2)."));
                            }
                        }
                    }
                    break;
                }

                case ESPERAR_JOGADOR: {
                    uint8_t qtd_leds = round_atual + 1;
                    int8_t botao_pressionado = -1;
                    uint8_t leituras_atuais = ler_estado_botoes();
                    static uint32_t tempo_ultimo_clique[4] = {0, 0, 0, 0};

                    for (int i = 0; i < 4; i++) {
                        bool agora_pressionado = tst_bit(leituras_atuais, i);
                        bool antes_pressionado = tst_bit(estado_botoes_anterior, i);

                        if (agora_pressionado && !antes_pressionado) {
                            if (tempo_atual - tempo_ultimo_clique[i] > 150) {
                                botao_pressionado = i;
                                set_bit(PORTD, pinos_leds[i]);
                                tempo_ultimo_clique[i] = tempo_atual;
                            }
                        } else if (!agora_pressionado && antes_pressionado) {
                            clr_bit(PORTD, pinos_leds[i]);
                            tempo_ultimo_clique[i] = tempo_atual;
                        }
                    }

                    estado_botoes_anterior = leituras_atuais;

                    if (botao_pressionado != -1) {
                        if (passo_jogador < qtd_leds) {
                            const char* nomes_cores[4] = {"VERMELHO", "AMARELO", "VERDE", "AZUL"};

                            resposta_jogador[passo_jogador] = botao_pressionado;
                            passo_jogador++;

                            Serial.print(F("-> Registrado ("));
                            Serial.print(passo_jogador);
                            Serial.print(F("/"));
                            Serial.print(qtd_leds);
                            Serial.print(F("): "));
                            Serial.println(nomes_cores[botao_pressionado]);

                            if (passo_jogador == qtd_leds) {
                                Serial.println(F("Sequencia preenchida! Aperte CONFIRMA para validar."));
                            }
                        } else {
                            Serial.println(F("Limite atingido! Aperte CONFIRMA para validar."));
                        }
                    }

                    if (confirma_pressionado) {
                        confirma_pressionado = false;
                        PORTD &= ~MASCARA_LEDS;

                        bool acertou = (passo_jogador == qtd_leds);
                        if (acertou) {
                            for (uint8_t i = 0; i < qtd_leds; i++) {
                                if (resposta_jogador[i] != sequencia[i]) {
                                    acertou = false;
                                    break;
                                }
                            }
                        }

                        if (acertou) {
                            Serial.println(F("ACERTOU a sequencia!"));
                            round_atual++;

                            if (round_atual > 4) {
                                Serial.println(F("\nMini-game concluido!"));
                                Serial.println(F("Dica desbloqueada: Foi encontrado um OCULOS e um OBJETO PONTIAGUDO na cena do crime\n"));
                                mostrar_tempo_restante(tempo_atual);
                                Serial.println(F("Digite a arma do crime!"));
                                estado_atual = MORSE;
                            } else {
                                Serial.println(F("\nRound concluido!"));
                                tempo_led_anterior = tempo_atual;
                                estado_leds = ESPERAR_PROXIMO_ROUND;
                            }
                        } else {
                            erros++;

                            if (erros < 3) {
                                penalidade_acumulada += 30000;

                                if (tempo_total >= 30000) {
                                    tempo_total -= 30000;
                                } else {
                                    tempo_total = 0;
                                }

                                Serial.print(F("ERROU a sequencia! (Erro "));
                                Serial.print(erros);
                                Serial.println(F("/3) Penalidade de 30s aplicada. Voltando para o Round 1..."));
                                mostrar_tempo_restante(tempo_atual);
                                Serial.println();

                                round_atual = 1;
                                tempo_led_anterior = tempo_atual;
                                estado_leds = ESPERAR_PROXIMO_ROUND;
                            }
                        }
                    }
                    break;
                }
            }
            break;
        }

        // 3º MINI-GAME: CÓDIGO MORSE
        case MORSE: {
            if (tempo_atual - tempoUltimaLeitura >= tempoDebounce) {
                tempoUltimaLeitura = tempo_atual;

                bool btnPonto = (ler_adc(1) < 512);
                bool btnTraco = (ler_adc(2) < 512);

                uint8_t estadoAtual = 0;
                if (btnPonto && btnTraco) estadoAtual = 3;
                else if (btnPonto) estadoAtual = 1;
                else if (btnTraco) estadoAtual = 2;

                if (estadoAtual != 0) {
                    if (estadoAtual == 3) {
                        estadoMaximo = 3;
                    } else if (estadoMaximo != 3) {
                        estadoMaximo = estadoAtual;
                    }
                }

                if (estadoAtual == 0 && estadoAnterior != 0) {
                    if (estadoMaximo == 3) {
                        if (letraAtual != "") {
                            Serial.println();
                            Serial.print(F("Letra confirmada: "));
                            Serial.println(letraAtual);

                            senhaDigitada += letraAtual + " ";

                            Serial.print(F("Palavra atual (em Morse): "));
                            Serial.println(senhaDigitada);

                            letraAtual = "";
                        }
                        else if (senhaDigitada != "") {
                            Serial.println();
                            Serial.println(F(">>> VERIFICANDO SENHA <<<"));

                            if (senhaDigitada == senhaCorreta) {
                                Serial.println("===============================");
                                Serial.println(F("\nMini-game concluido!\nDica desbloqueada: Foi encontrado um FIO DE CABELO RUIVO na cena do crime!\n"));
                                mostrar_tempo_restante(tempo_atual);
                                Serial.println("===============================");
                                estado_atual = DISCAGEM; // Avança para o 4º mini-game
                            } else {
                                registrar_erro(tempo_atual);
                                senhaDigitada = "";
                            }
                        }
                    }
                    else if (estadoMaximo == 1) {
                        letraAtual += ".";
                        Serial.print(".");
                    }
                    else if (estadoMaximo == 2) {
                        letraAtual += "-";
                        Serial.print("-");
                    }

                    estadoMaximo = 0;
                }

                estadoAnterior = estadoAtual;
            }
            break;
        }

        // 4º MINI-GAME: DISCAGEM E DECLARAÇÃO DO ASSASSINO
        case DISCAGEM: {
            char tecla = lerTeclado();
            Serial.println(F("Disque para fazer sua denuncia:"));
            if (tecla != '\0' && (meu_millis() - ultimo_toque >= TEMPO_DEBOUNCE)) {
                ultimo_toque = meu_millis();

                if (policiaAtendeu == false) {
                    discaNumero(tecla);
                } else {
                    guardaSenha(tecla);
                }
            }
            break;
        }

        case VITORIA:
            som_sirene();
            break;

        case DERROTA:
            som_facada();
            break;
    }
}