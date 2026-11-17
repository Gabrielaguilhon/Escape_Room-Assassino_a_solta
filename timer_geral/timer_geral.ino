#include <avr/io.h>
#include <avr/interrupt.h>
// macros de bit
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))
volatile uint32_t ms = 0;
uint32_t contagem_atual = 0;
ISR(TIMER1_COMPA_vect) { // roda a cada 1 ms
  ms++;
  }
uint32_t meu_primeiro_millis() { // millis()
  return ms;
  }
uint32_t tempo_total = 12UL * 60UL * 1000UL; //UL = unsigned long - positivo e longo
uint32_t penalidade_acumulada = 0;

void setup() {
  set_bit(DDRB, PB5);
  cli();
  TCCR1A = 0; // apaga o que a IDE configurou
  // modo CTC, topo = OCR1A, N = 64: passo de 4 us
  TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10);
  OCR1A = 249; // 250 passos = 1 ms
  TIMSK1 = (1 << OCIE1A); // liga a interrupção
  sei();
  }
void loop() {
  uint32_t tempo_atual = meu_primeiro_millis();
  uint32_t tempo_consumido = tempo_atual - penalidade_acumulada;

  if (tempo_total > tempo_consumido){
    uint32_t tempo_restante = tempo_total - tempo_consumido;
  }
  else{
    //O tempo acabou (som de facadas)
  }
  }
