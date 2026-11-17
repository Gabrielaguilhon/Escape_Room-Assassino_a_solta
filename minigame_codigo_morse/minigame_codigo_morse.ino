#include <avr/io.h>
#include <avr/interrupt.h> 

// Macros de bit
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))

String letraAtual = "";
String senhaDigitada = "";
String senhaCorreta = "..-. .- -.-. .- "; // FACA

// Maquina de estados
uint32_t tempoUltimaLeitura = 0;
const uint32_t tempoDebounce = 50; 
uint8_t estadoAnterior = 0; 
uint8_t estadoMaximo = 0; 

volatile uint32_t ms = 0; 

ISR(TIMER1_COMPA_vect) {
  ms++;
}

// Retorna os milissegundos
uint32_t meu_millis() {
  uint32_t tempo;
  cli();       
  tempo = ms;
  sei();       
  return tempo;
}

// Leitura do ADC com dummy read pra evitar ghosting
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
  
  cli(); 
  
  // Timer1 para 1ms (Modo CTC)
  TCCR1A = 0;
  TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10); // Prescaler 64
  OCR1A = 249;                                       
  TIMSK1 = (1 << OCIE1A);                            
  
  // A1 (PC1) - Botao Ponto
  clr_bit(DDRC, PC1);  
  set_bit(PORTC, PC1); 
  
  // A2 (PC2) - Botao Traco
  clr_bit(DDRC, PC2);  
  set_bit(PORTC, PC2); 
  
  // Config ADC
  ADMUX = (1 << REFS0);
  ADCSRA = (1 << ADEN) | (1 << ADPS2) | (1 << ADPS1) | (1 << ADPS0);
  
  sei(); 
  
  Serial.println("Minigame Codigo Morse iniciado");
  Serial.println("Digite a arma do crime!");
  delay(200); 
}

void loop() {
  uint32_t tempoAtual = meu_millis(); 
  
  if (tempoAtual - tempoUltimaLeitura >= tempoDebounce) {
    tempoUltimaLeitura = tempoAtual;
    
    bool btnPonto = (ler_adc(1) < 512); 
    bool btnTraco = (ler_adc(2) < 512);
    
    uint8_t estadoAtual = 0;
    
    if (btnPonto && btnTraco) estadoAtual = 3;
    else if (btnPonto) estadoAtual = 1;
    else if (btnTraco) estadoAtual = 2;

    if (estadoAtual != 0) {
      if (estadoAtual == 3) {
        estadoMaximo = 3; 
      } 
      else if (estadoMaximo != 3) {
        estadoMaximo = estadoAtual; 
      }
    }

    // Borda de descida
    if (estadoAtual == 0 && estadoAnterior != 0) {
      
      if (estadoMaximo == 3) { 
         
         if (letraAtual != "") {
             Serial.println();
             Serial.print("Letra confirmada: ");
             Serial.println(letraAtual);
             
             senhaDigitada += letraAtual + " "; 
             
             Serial.print("Palavra atual (em Morse): ");
             Serial.println(senhaDigitada);
             
             letraAtual = ""; 
         }
         else if (senhaDigitada != "") {
             Serial.println();
             Serial.println(">>> VERIFICANDO SENHA <<<");
             
             if (senhaDigitada == senhaCorreta) {
                Serial.println("===============================");
                Serial.println("\nMini-game concluido!\nDica desbloqueada: Foi encontrado um FIO DE CABELO RUIVO na cena do crime!\n");
                Serial.println("===============================");
             } 
             else {
                Serial.println("--- ARMA ERRADA! Tente novamente. ---");
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
}