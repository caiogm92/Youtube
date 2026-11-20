# Santos FC — O Eterno Gigante

Documentário cinematográfico de ~5 minutos (5:09), 1920×1080, 30 fps, estética de documentário esportivo premium.

## Como gerar o vídeo

```bash
pip install numpy pillow global-land-mask
python3 prep_audio.py          # narração: encurta pausas, ajusta andamento, mede frases
python3 render.py              # quadros 1080p em blocos paralelos  (--preview = 540p rápido)
python3 render.py --still=12,64,300   # quadros de conferência em build/
python3 mix.py                 # narração + trilha com ducking + normalização -14 LUFS
./finalize.sh                  # junta vídeo e áudio em output/
```

## Estrutura

| Capítulo | Início | Conteúdo visual |
|---|---|---|
| I — Antes de ser lenda | 0:00 | mar ao amanhecer, arquibancada antiga, escudo, camisa branca, cartela "SANTOS FC · 1912 — ETERNAMENTE." |
| II — O mundo aos seus pés | 0:41 | estádio lotado (anos 1950/60), Pelé jovem, mapa das finais de 1962/63, as duas estrelas do escudo, cartela 1962/1963 |
| III — Uma camisa que nunca perdeu sua história | 1:38 | o tempo passando, torcida, Neymar (detalhe da camisa 10), mapa Libertadores 2011, cartela 2011 |
| IV — Quando o gigante precisou lutar | 2:41 | estádio vazio sob chuva, escudo apagado, Pelé (legado), torcida, "2024 — O RETORNO.", camisas 9 e 10 |
| V — Eternamente Santos | 3:46 | menino a caminho do estádio, pai e filho, arquibancada, Pelé e Neymar, final com o escudo |

Cada corte é sincronizado com a frase correspondente da narração (`timeline.py` + `build/phrases.json`).

## Fontes de mídia

- **Fotografias** (`assets/`): enviadas pelo autor do projeto — Pelé (três fotos históricas), escudo, Neymar e Gabriel Barbosa (temporada 2025). Os direitos dessas imagens pertencem aos seus detentores; confirme o licenciamento antes de publicar.
- **B-roll ilustrativo gerado por IA** (`assets/broll_*.jpg`, ElevenLabs/Seedream): torcida com bandeiras, menino caminhando até o estádio, pai e filho na arquibancada. São cenas genéricas, **não retratam pessoas nem jogos reais**.
- **Planos procedurais** (gerados por código em `render.py`): mar ao amanhecer, estádio vazio na chuva, bandeira alvinegra tremulando, mapa pontilhado (contornos de `global-land-mask`).
- **Narração**: ElevenLabs, voz "Nassif — Documentary" (pt-BR), modelo eleven_v4.
- **Trilha**: ElevenLabs Music v2.5, três faixas originais instrumentais. Caps. IV e V reaproveitam essas faixas: o tema de piano em versão mais grave no Cap. IV e a faixa do Cap. II como reprise no final.
- **Tipografia**: Cinzel, Oswald, Bebas Neue (Google Fonts, licença OFL).

## Checagem de fatos

| Afirmação | Situação |
|---|---|
| Fundação em 1912, na cidade de Santos | ✔ 14/04/1912 |
| Bicampeão da Libertadores (1962, 1963) | ✔ finais contra Peñarol (1962) e Boca Juniors (1963) |
| Bicampeão mundial (1962, 1963) | ✔ Intercontinental contra Benfica (1962) e Milan (1963) |
| Mapa: Montevidéu, Buenos Aires, Lisboa, Milão | ✔ cidades que receberam jogos dessas finais (1ª partida de 1962 em Montevidéu; Bombonera em 1963; Estádio da Luz em 1962; San Siro em 1963) |
| 2011 — tricampeão da Libertadores, 48 anos depois de 1963 | ✔ final contra o Peñarol (1ª partida em Montevidéu) |
| 2023 — primeiro rebaixamento, 111 anos de existência | ✔ 1912 → 2023 |
| 2024 — campeão da Série B e de volta à elite | ✔ |

## O que trocar para uma versão de transmissão

O roteiro original pede imagens aéreas reais de Santos e da Vila Belmiro, além de vídeos de arquivo (gols de 1962/63 e da Libertadores de 2011). Quando houver material licenciado (acervo do clube, agências), basta salvar em `assets/` e apontar o plano correspondente em `timeline.py` (tipo `broll` para imagens 16:9).
