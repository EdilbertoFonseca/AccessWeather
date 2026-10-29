# AccessWeather

Add-on para o leitor de tela [NVDA](https://www.nvaccess.org/) que anuncia as
condições atuais e a previsão do tempo usando a API
[Open-Meteo](https://open-meteo.com/), sem chave de API.

## Instalação

- Pela **Add-on Store** do NVDA (Ferramentas → Loja de complementos), ou
- Baixando o `.nvda-addon` na aba
  [Releases](https://github.com/tadeujrtec/AccessWeather/releases) e abrindo o
  arquivo.

## Uso

Atalho único: `NVDA + Shift + W`, tocado uma ou mais vezes:

| Toques | Ação |
|---|---|
| 1x | Anuncia o clima atual do local padrão |
| 2x | Lista das próximas 24 horas |
| 3x | Lista dos próximos dias |
| 4x | Abre as configurações do NVDA em AccessWeather |
| 5x | Liga/desliga os anúncios personalizados do local |

O tempo de multi-toque é o mesmo configurado no NVDA. Só a ação do número final
de toques dispara.

## Recursos

- Locais salvos, com local padrão, reordenação e busca por nome.
- Campos de anúncio personalizáveis e reordenáveis por local (`Alt+setas`);
  `F2` lê o valor do campo selecionado para o local escolhido.
- Anúncios automáticos por local, em intervalo ajustável (1 a 360 minutos).
- Sequências de beeps por local e beeps globais antes do anúncio de 1 toque.
- Cache offline e formatação em português.
- Velocidade e direção do vento (rosa dos ventos de 8 pontos).
- Rajadas de vento, nebulosidade, visibilidade e pressão atmosférica.
- Índice UV com classificação e qualidade do ar (AQI e PM2.5).
- Chuva contínua, pancadas e horas de chuva no dia.
- Nascer e pôr do sol, nascer e pôr da lua e fase da lua nos anúncios.
- Horas de sol, duração do dia e sensação máxima e mínima.
- Unidades (métrico/imperial), vento, formato de hora e de data configuráveis.
- Janela de novidades uma vez por versão (com opção de desligar e botão para reler).

## Dados

O add-on guarda tudo em `%APPDATA%\nvda\accessWeather\` (`settings.json`,
`locations.json` e `cache.json`).

## Estrutura

```text
addon/accessWeather/
├── manifest.ini
└── globalPlugins/accessWeather/
    ├── __init__.py
    ├── dialogs.py
    ├── playback.py
    └── core/
```

## Licença

[GPL v2 ou posterior](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html).
