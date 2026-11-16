#include <avr/io.h>

// Macros para operações de bit exigidas na disciplina
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))

String letraAtual = "";
String senhaDigitada = "";
// A senha correta: FACA (com espaço no final de cada letra)
String senhaCorreta = "..-. .- -.-. .- ";

// Variáveis para a máquina de estados não bloqueante
uint32_t tempoUltimaLeitura = 0;
const uint32_t tempoDebounce = 50; 
uint8_t estadoAnterior = 0; 
uint8_t estadoMaximo = 0; // Guarda a combinação máxima pressionada

// Função de leitura corrigida (Leitura Dupla contra Ghosting do ADC)
uint16_t ler_adc(uint8_t canal) {
  ADMUX = (ADMUX & 0xF0) | canal; 
  
  set_bit(ADCSRA, ADSC);          
  while (tst_bit(ADCSRA, ADSC));  
  
  set_bit(ADCSRA, ADSC);          
  while (tst_bit(ADCSRA, ADSC));  
  
  return ADC;
}

void setup() {
  Serial.begin(9600);
  
  // Configurar A1 (PC1) - Fio Vermelho (Botão Ponto)
  clr_bit(DDRC, PC1);  
  set_bit(PORTC, PC1); // Liga pull-up interno
  
  // Configurar A2 (PC2) - Fio Amarelo (Botão Traço)
  clr_bit(DDRC, PC2);  
  set_bit(PORTC, PC2); // Liga pull-up interno
  
  // Configuração do ADC (Referência 5V e Prescaler 128)
  ADMUX = (1 << REFS0);
  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
  
  Serial.println("Minigame Codigo Morse iniciado");
  Serial.println("Digite a arma do crime!");
  delay(200); // Atraso de estabilização
}

void loop() {
  uint32_t tempoAtual = millis(); 
  
  if (tempoAtual - tempoUltimaLeitura >= tempoDebounce) {
    tempoUltimaLeitura = tempoAtual;
    
    bool btnPonto = (ler_adc(1) < 512); 
    bool btnTraco = (ler_adc(2) < 512);
    
    uint8_t estadoAtual = 0;
    
    if (btnPonto && btnTraco) estadoAtual = 3;
    else if (btnPonto) estadoAtual = 1;
    else if (btnTraco) estadoAtual = 2;

    // Atualiza o pico da jogada enquanto os botões estão sendo pressionados
    if (estadoAtual != 0) {
      if (estadoAtual == 3) {
        estadoMaximo = 3; 
      } 
      else if (estadoMaximo != 3) {
        estadoMaximo = estadoAtual; 
      }
    }

    // AÇÃO NA BORDA DE DESCIDA: Dispara quando todos os botões forem soltos
    if (estadoAtual == 0 && estadoAnterior != 0) {
      
      if (estadoMaximo == 3) { // Soltou após apertar os dois botões
         
         // 1. Se tem algo digitado, confirma a LETRA
         if (letraAtual != "") {
             Serial.println();
             Serial.print("Letra confirmada: ");
             Serial.println(letraAtual);
             
             senhaDigitada += letraAtual + " "; // Adiciona na palavra com espaço
             
             Serial.print("Palavra atual (em Morse): ");
             Serial.println(senhaDigitada);
             
             letraAtual = ""; // Zera a letra atual para a próxima
         }
         // 2. Se a letra atual está vazia (Confirmação Dupla), avalia a PALAVRA inteira
         else if (senhaDigitada != "") {
             Serial.println();
             Serial.println(">>> VERIFICANDO SENHA <<<");
             
             if (senhaDigitada == senhaCorreta) {
                Serial.println("===============================");
                Serial.println("\nMini-game concluido!\nDica desbloqueada: Foi encontrado um FIO DE CABELO RUIVO na cena do crime!\n");
                Serial.println("===============================");
                
                // Aqui você pode mudar a variável de fase para o próximo puzzle
             } 
             else {
                Serial.println("--- ARMA ERRADA! Tente novamente. ---");
                senhaDigitada = ""; // Apaga toda a palavra para tentar do zero
             }
         }
      } 
      else if (estadoMaximo == 1) { // Soltou após apertar só o Ponto
         letraAtual += ".";
         Serial.print(".");
      } 
      else if (estadoMaximo == 2) { // Soltou após apertar só o Traço
         letraAtual += "-";
         Serial.print("-");
      }
      
      estadoMaximo = 0; // Zera a memória para a próxima jogada
    }
    
    estadoAnterior = estadoAtual;
  }
}