#include <avr/io.h>
#include <stdlib.h> // Necessário para a função itoa() (converte inteiro para string)
#include <util/delay.h> // Apenas para segurar a velocidade do print no monitor

// macros de bit
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))
 
#define LIMIAR_ALTO 700 // acima disso: ruídos
#define LIMIAR_BAIXO 600 // abaixo disso: ruídos
 
//uint8_t radio_sintonizado = 0; //começa não sintonizado
 
void sintoniza_radio(uint16_t valor) {
  if (valor > LIMIAR_ALTO || valor < LIMIAR_BAIXO) {
    meu_tone(440);
    Serial.println("Voce ainda nao conseguiu sintonizar o radio, esta perdendo tempo...");
  } else{
       //radio_sintonizado = 1;
       meu_noTone();
       Serial.println("Sinal Radio: ");
       //Serial.println(valor); // Envia o número lido
       Serial.println("Radio sintonizado");
    }
  }
 
uint16_t meu_analogRead(uint8_t canal) {
  ADMUX = (ADMUX & 0xF0) | canal; // escolhe A0..A5
  set_bit(ADCSRA, ADSC);
   //começa a conversão
  while (tst_bit(ADCSRA, ADSC));
   //espera terminar a leitura
  return ADC;
}
 
void meu_tone(uint16_t frequencia) {
  set_bit(DDRD, PD6);
  // tone(11, frequencia), frequencia >= 245 Hz
  // f = 16 MHz / (2 * 128 * (OCR2A + 1))
  OCR0A = 62500 / frequencia- 1;
  // modo CTC, D11 (OC2A) inverte a cada volta
  TCCR0A = (1 << COM0A0) | (1 << WGM01);
  TCCR0B = (1 << CS01) | (1 << CS00); // N = 128: liga
}
 
void meu_noTone() {
  // noTone(11)
  TCCR0B = 0;
  // para o timer
  TCCR0A = 0;
  // D11 volta a ser pino comum
  clr_bit(PORTD, PD6);
}
 
void setup() {
  Serial.begin(9600);
  //set_bit(DDRB, PB3);
  ADMUX = (1 << REFS0);
  // referência = 5 V
  ADCSRA = (1 << ADEN)
  | (1 << ADPS2) | (1 << ADPS1) // divisor 128:
  | (1 << ADPS0);
  // 16 MHz/128 = 125 kHz
}
 
void loop() {
  uint16_t valor = meu_analogRead(0);
  sintoniza_radio(valor); // A0
  Serial.println(valor);
 
}
