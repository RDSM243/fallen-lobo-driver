# Fallen Lobo Wireless — Driver, Interface Gráfica & AppImage para Linux

> **Aviso Legal:** Este é um projeto **independente e não-oficial** de código aberto, desenvolvido pela comunidade para fins de interoperabilidade no Linux. Não possui vínculo, patrocínio ou endosso da Fallen Gear ou da Compx. Todos os gráficos e ícones da interface são originais.

Implementação completa em userspace (`hidraw`) e interface gráfica PyQt6 para o **Mouse Gamer Fallen Lobo Wireless** (chipset Compx `3554:F53C` via dongle 2.4GHz e `3554:F511` via cabo USB-C, sensor PixArt PAW3395).

## Requisitos

- **Python 3** (stdlib para a CLI `lobo-ctl`)
- **PyQt6** (para a interface gráfica e AppImage)
- Permissão `udev` para acesso `hidraw` (configurada automaticamente pelo `install.sh` ou pelo botão de reparo dentro da interface)

## Instalação

Você pode baixar o **`Fallen-Lobo-Wireless-x86_64.AppImage`** na página de [Releases](https://github.com/RDSM243/fallen-lobo-driver/releases) e executá-lo diretamente, ou instalar no sistema pelo repositório:

```bash
git clone https://github.com/RDSM243/fallen-lobo-driver.git
cd fallen-lobo-driver
# Coloque o AppImage baixado da Release nesta pasta ou gere localmente com:
./build_appimage.sh
./install.sh
```

O script instala a regra `udev` em `/etc/udev/rules.d/70-fallen-lobo-wireless.rules`, copia o AppImage para `~/AppImages/fallen_lobo_wireless.appimage`, registra o ícone no menu de aplicativos e cria o link simbólico `~/.local/bin/lobo-ctl`.

## Funcionalidades

- **Botões (6 teclas):** Remapeamento completo (cliques padrão, DPI Loop/DPI+/DPI-/Trava de DPI, Fire Key, atalhos de teclado, 18 comandos multimídia/sistema, Macros, troca de Polling Rate, Luz ON/OFF e Desabilitar), **Debounce (`0–30 ms`)**, **4 Perfis** e **Importar/Exportar (`.json`)**.
- **Sensor PAW3395 & DPI:** `1` a `8` estágios de DPI (`50` a `26.000 DPI`), cor RGB por estágio, **Polling Rate (`125–4000 Hz`)**, **LOD (`1/2 mm`)**, **Motion Sync**, **Angle Snapping**, **Ripple Control** e modo de energia (`LP` / `HP` / `Corded`).
- **Macros:** Gravador de teclas em tempo real com atraso automático ou fixo, edição de passos e gravação na memória Flash do mouse.
- **Iluminação RGB:** 7 modos de efeito, brilho, velocidade, paleta de cores + roda RGB, desligar ao mover e tempo de inatividade.
- **Configurações:** Leitura de bateria (`%` e `mV`), versão de firmware do receptor e do mouse, tempo de espera, modo de longa distância, LED do receptor e restauração de fábrica.

## Uso via CLI (`lobo-ctl`)

```bash
lobo-ctl status                  # Status completo (bateria, firmware, DPI, polling rate, sensor)
lobo-ctl battery --json          # Saída JSON ideal para Waybar / Polybar / Noctalia
lobo-ctl set-dpi 1 800           # Define 800 DPI no estágio 1
lobo-ctl polling-rate 1000       # 125, 250, 500, 1000, 2000, 4000
```

## Licença

Distribuído sob a licença [GNU GPL v3 (GPL-3.0)](LICENSE). Veja [COPYRIGHT](COPYRIGHT) para mais detalhes.
