#include <avr/io.h>
#include <stdlib.h> // Necessário para a função itoa() (converte inteiro para string)
#include <util/delay.h> // Apenas para segurar a velocidade do print no monitor

// macros de bit
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))

uint16_t meu_analogRead(uint8_t canal) {
ADMUX = (ADMUX & 0xF0) | canal; // escolhe A0..A5
set_bit(ADCSRA, ADSC);
// começa a conversão
while (tst_bit(ADCSRA, ADSC));
// espera terminar a leitura
return ADC;
}

void meu_tone(uint16_t frequencia) {
// tone(11, frequencia), frequencia >= 245 Hz
// f = 16 MHz / (2 * 128 * (OCR2A + 1))
OCR2A = 62500 / frequencia- 1;
// modo CTC, D11 (OC2A) inverte a cada volta
TCCR2A = (1 << COM2A0) | (1 << WGM21);
TCCR2B = (1 << CS22) | (1 << CS20); // N = 128: liga
}

void meu_noTone() {
// noTone(11)
TCCR2B = 0;
// para o timer
TCCR2A = 0;
// D11 volta a ser pino comum
clr_bit(PORTB, PB3);
}
  
void setup() {
  Serial.begin(9600);
  set_bit(DDRB, PB3);
  set_bit(DDRB, PB5);
  ADMUX = (1 << REFS0);
  // referência = 5 V
  ADCSRA = (1 << ADEN)
  // liga o ADC
  | (1 << ADPS2) | (1 << ADPS1) // divisor 128:
  | (1 << ADPS0);
  // 16 MHz/128 = 125 kHz
}
void loop() {
  uint16_t valor = meu_analogRead(0); // A0
  
  if (valor > 512) {
    set_bit(PORTB, PB5);
    meu_tone(440);
    delay(200);
    meu_noTone();
    delay(800);
    Serial.println("Sinal Radio: ");
  	Serial.println(valor); // Envia o número lido
    Serial.println("Radio sintonizado");

  } else {
    clr_bit(PORTB, PB5);
    Serial.println("Voce ainda nao conseguiu sintonizar o radio, esta perdendo tempo...");

    }
    
    _delay_ms(250); // Delay temporário apenas para não travar seu monitor serial
  
}