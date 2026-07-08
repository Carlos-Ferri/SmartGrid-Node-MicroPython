# SmartGrid-Node-MicroPython
Sistema de Gerenciamento de Energia (EMS) em MicroPython para microredes. Um ESP32-C3 atua na borda adquirindo dados via UART e transmitindo por UDP. O núcleo é um Raspberry Pi Pico 2 W operando como Access Point assíncrono (uasyncio), que centraliza a telemetria e hospeda uma API REST para supervisão em tempo real.
