#include <SoftwareWire.h>
#include <avr/io.h>
#include <avr/interrupt.h>
#include <stdlib.h>

// Macros obrigatórias para manipulação de bits
#define set_bit(reg, bit) ((reg) |= (1 << (bit)))
#define clr_bit(reg, bit) ((reg) &= ~(1 << (bit)))
#define cpl_bit(reg, bit) ((reg) ^= (1 << (bit)))
#define tst_bit(reg, bit) ((reg) & (1 << (bit)))

// 1. Configuração do I2C em pinos digitais[cite: 11]
const int SDA_PIN = 8;
const int SCL_PIN = 9;
SoftwareWire softWire(SDA_PIN, SCL_PIN);

// Configuração da variável de tempo
volatile uint32_t ms = 0;

uint32_t ultimo_toque = 0;
const uint32_t TEMPO_DEBOUNCE = 200; // 200ms de intervalo mínimo entre leituras

// Endereço I2C do módulo preto (costuma ser 0x27 ou 0x20)
const uint8_t ENDERECO_TECLADO = 0x27; 

// 2. Mapa do teclado sem a coluna A, B, C, D
char mapaTeclas[4][3] = {
  {'1', '2', '3'},
  {'4', '5', '6'},
  {'7', '8', '9'},
  {'*', '0', '#'}
};

// 3. Mapeamento dos bits do PCF8574 ignorando a porta P3
// Linhas (4 fios da esquerda do teclado): P0, P1, P2, P4
uint8_t bitsLinhas[4] = {0, 1, 2, 4};
// Colunas (3 fios da direita do teclado): P5, P6, P7
uint8_t bitsColunas[3] = {5, 6, 7};

//Discagem inicial a ser feita
char discagem[] = "190";
//Vetor para guardar até 3 digitos + 1 caractere nulo de final de texto
char discagemRealizada[4] = "";
int indiceDiscagem = 0;
bool policiaAtendeu = false;

//Senha solicitada, indica "AnaB"
char senha_real[] = "166111";
// Vetor para guardar até 6 dígitos + 1 caractere nulo de final de texto
char senha_digitada[7] = ""; 
int indiceSenha = 0;

// Conta o tempo em milissegundos
ISR(TIMER1_COMPA_vect) {
    ms++;
}

// Função equivalente a millis()
uint32_t meu_millis() {
    uint32_t tempo;
    cli();
    tempo = ms;
    sei();
    return tempo;
}

// Função que faz o trabalho da biblioteca Keypad varrendo as teclas
char lerTeclado() {
  for (int linha = 0; linha < 4; linha++) {
    // Joga sinal BAIXO (0) na linha atual e ALTO (1) nas outras
    uint8_t valorEscrita = ~(1 << bitsLinhas[linha]);
    
    softWire.beginTransmission(ENDERECO_TECLADO);
    softWire.write(valorEscrita);
    softWire.endTransmission();

    // Lê o estado das colunas para ver se o sinal passou por alguma tecla
    softWire.requestFrom(ENDERECO_TECLADO, (uint8_t)1);
    if (softWire.available()) {
      uint8_t leitura = softWire.read();
      
      for (int coluna = 0; coluna < 3; coluna++) {
        // Se a coluna correspondente estiver em BAIXO (0), a tecla foi apertada
        if ((leitura & (1 << bitsColunas[coluna])) == 0) {
          return mapaTeclas[linha][coluna];
        }
      }
    }
  }
  return '\0'; // Retorna nulo se nada foi pressionado
}

void guardaSenha(char tecla){
   if (tecla != '\0') {
    Serial.print("Tecla pressionada: ");
    Serial.println(tecla);
    
    // 1. Lógica de CONFIRMAR a senha (tecla #)
    if (tecla == '#') {
      senha_digitada[indiceSenha] = '\0'; // Fecha o texto para o C/C++ entender que acabou
      
      Serial.print("Jogador tentou o suspeito: ");
      Serial.println(senha_digitada);
      
      // Aqui faz a verificação
      // strcmp compara dois textos. Se o resultado for 0, eles são iguais.
      if (strcmp(senha_digitada, senha_real)==0) {
        Serial.println("ACERTOU! Sirene tocando...");
        // Adicionar o buzzer neste ponto (função meuTone() já criada em outro momento)
      } else {
        Serial.println("ERROU! Barulho de facada...");
        // Adicionar aqui a função de penalidade de tempo e som de derrota (função noTone())
      }
      
      // RESET para a próxima tentativa: zera o índice e apaga o vetor
      indiceSenha = 0;
      senha_digitada[0] = '\0';
      
    } 
    // 2. Lógica de APAGAR (tecla *)
    else if (tecla == '*') {
      if (indiceSenha > 0) {
        indiceSenha--; // Volta uma posição
        senha_digitada[indiceSenha] = '\0'; // Apaga o caractere daquela posição
        Serial.println("Apagou o ultimo digito.");
      }
    } 
    // 3. Lógica de GUARDAR NÚMEROS (0 a 9)
    else {
      // Verifica se ainda tem espaço no vetor (tamanho máximo 19)
      if (indiceSenha < 6) {
        senha_digitada[indiceSenha] = tecla; // Salva o número na posição atual
        indiceSenha++;                       // Avança para a próxima posição vazia
        senha_digitada[indiceSenha] = '\0';  // Já fecha o texto provisoriamente
        
        Serial.print("Senha parcial: ");
        Serial.println(senha_digitada);
      } else {
        Serial.println("Limite maximo de caracteres atingido!");
      }
    }
  }
}

void discaNumero(char tecla){
   if (tecla != '\0') {
    Serial.print("Tecla pressionada: ");
    Serial.println(tecla);
    
    // 1. Lógica de confirmar discagem (tecla #)
    if (tecla == '#') {
      discagemRealizada[indiceDiscagem] = '\0'; 
      
      //Serial.print("Jogador discou: ");
      //Serial.println(discagemRealizada);
      
      if (strcmp(discagemRealizada, discagem)==0) {
        Serial.println("Você foi atendido! Pode indicar o assassino.");
        
        // MUDANÇA DE ESTADO: Avisa ao loop que o jogador passou de fase!
        policiaAtendeu = true; 
        
      } else {
        Serial.println("Sua discagem está inadequada! Repita, por favor!");
      }
      
      // RESET para a próxima tentativa
      indiceDiscagem = 0;
      discagemRealizada[0] = '\0';
      
    } 
    // 2. Lógica de APAGAR (tecla *)
    else if (tecla == '*') {
      if (indiceDiscagem > 0) {
        indiceDiscagem--; 
        discagemRealizada[indiceDiscagem] = '\0'; // CORRIGIDO
        Serial.println("Apagou o ultimo digito.");
      }
    } 
    // 3. Lógica de GUARDAR NÚMEROS (0 a 9)
    else {
      if (indiceDiscagem < 3) {
        discagemRealizada[indiceDiscagem] = tecla; // CORRIGIDO
        indiceDiscagem++;                       
        discagemRealizada[indiceDiscagem] = '\0';  // CORRIGIDO
        
        Serial.print("Discagem parcial: ");
        Serial.println(discagemRealizada);
      } else {
        Serial.println("Limite maximo de caracteres atingido!");
      }
    }
  }
}
void setup() {
  Serial.begin(9600);
  
  // Inicia o I2C nos pinos digitais para o teclado
  softWire.begin();

  // Configuração do Timer1 para contar a cada 1 ms sem bloquear o código
  cli(); 
  TCCR1A = 0; 
  TCCR1B = (1 << WGM12) | (1 << CS11) | (1 << CS10); 
  OCR1A = 249; 
  TIMSK1 = (1 << OCIE1A); 
  sei();
  
  Serial.println("Teclado via SoftwareWire iniciado!");
}

void loop() {
  char tecla = lerTeclado();
  // Só entra no if se uma tecla foi pressionada E já passou o tempo do debounce
  if (tecla != '\0' && (meu_millis() - ultimo_toque >= TEMPO_DEBOUNCE)) {
    
    // Atualiza o rastreador de tempo
    ultimo_toque = meu_millis(); 
    
    // Executa a máquina de estados
    if (policiaAtendeu == false) {
      discaNumero(tecla); 
    } else {
      guardaSenha(tecla); 
    }
  }

}