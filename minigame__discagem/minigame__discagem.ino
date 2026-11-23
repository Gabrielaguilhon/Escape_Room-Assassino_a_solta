#include <SoftwareWire.h>

// 1. Configuração do I2C em pinos digitais[cite: 11]
const int SDA_PIN = 8;
const int SCL_PIN = 9;
SoftwareWire softWire(SDA_PIN, SCL_PIN);

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
//Senha solicitada
char senha_real[] = "1661";
// Vetor para guardar até 19 dígitos + 1 caractere nulo de final de texto
char senha_digitada[20] = ""; 
int indice = 0;

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
      senha_digitada[indice] = '\0'; // Fecha o texto para o C/C++ entender que acabou
      
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
      indice = 0;
      senha_digitada[0] = '\0';
      
    } 
    // 2. Lógica de APAGAR (tecla *)
    else if (tecla == '*') {
      if (indice > 0) {
        indice--; // Volta uma posição
        senha_digitada[indice] = '\0'; // Apaga o caractere daquela posição
        Serial.println("Apagou o ultimo digito.");
      }
    } 
    // 3. Lógica de GUARDAR NÚMEROS (0 a 9)
    else {
      // Verifica se ainda tem espaço no vetor (tamanho máximo 19)
      if (indice < 19) {
        senha_digitada[indice] = tecla; // Salva o número na posição atual
        indice++;                       // Avança para a próxima posição vazia
        senha_digitada[indice] = '\0';  // Já fecha o texto provisoriamente
        
        Serial.print("Senha parcial: ");
        Serial.println(senha_digitada);
      } else {
        Serial.println("Limite maximo de caracteres atingido!");
      }
    }
    delay(200);
  }
}

void setup() {
  Serial.begin(9600);
  
  // Inicia o I2C nos pinos digitais para o teclado
  softWire.begin();
  
  Serial.println("Teclado via SoftwareWire iniciado!");
}

void loop() {
  char tecla = lerTeclado();
  guardaSenha(tecla);

}
